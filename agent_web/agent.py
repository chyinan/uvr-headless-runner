"""One tool-calling loop. It submits work and then waits for the real job."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request

from agent_web.service import ServiceError
from agent_web.spec import TARGETS, load_presets

SUBMIT_TOOLS = {"create_preview", "run_full"}
READONLY_TOOLS = {"inspect_task", "list_models"}


class LLMError(RuntimeError):
    pass


class Agent:
    def __init__(self, service, settings, catalog, hardware=None, complete=None):
        self.service = service
        self.settings = settings
        self.catalog = catalog
        self.hardware = hardware
        self.complete = complete or _openai_complete

    def run(self, task_id: str, selected_task_ids: list[str] | None = None) -> None:
        selected = _clean_ids(selected_task_ids) or [task_id]
        if task_id not in selected:
            selected = [task_id, *selected]
        try:
            text, refs = self._loop(task_id, selected)
        except LLMError as exc:
            text, refs = str(exc), []
        self.service.add_message(task_id, "assistant", text, refs)

    def _loop(self, task_id: str, selected: list[str]) -> tuple[str, list]:
        if not self.settings.llm_configured and self.complete is _openai_complete:
            raise LLMError("还没有配置语言模型。手动试听和整首处理可以直接用；对话需要在 agent_web/config.json 里填写接口地址、模型和密钥。")
        messages = self.service.list_messages(task_id)
        if not messages or messages[-1]["role"] != "user":
            raise LLMError("没有待回复的用户消息")
        message_id = messages[-1]["id"]
        transcript = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(self._context(task_id, selected), ensure_ascii=False)},
        ]
        for item in messages[-12:]:
            transcript.append({"role": item["role"], "content": item["content"][:4000]})
        collected = []
        final = ""
        for _ in range(6):
            reply = self.complete(self.settings, transcript, _tools())
            tool_calls = reply.get("tool_calls") or []
            content = (reply.get("content") or "").strip()
            if not tool_calls:
                final = content
                break
            transcript.append({"role": "assistant", "content": reply.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                name, arguments = _parse_call(call)
                result = self._call(task_id, message_id, name, arguments, selected)
                result["name"] = name
                collected.append(result)
                transcript.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "content": json.dumps(result, ensure_ascii=False)[:6000],
                    }
                )
            if any(item.get("ok") and item.get("name") in SUBMIT_TOOLS for item in collected):
                final = content
                break
        else:
            final = "这一轮工具调用已到上限。下面是已经发生的结果。"
        fact = _summarize(collected)
        text = final.strip()
        submitted = any(item.get("ok") and item.get("name") in SUBMIT_TOOLS for item in collected)
        if submitted and "已提交" not in text:
            text = f"{text}\n{fact}".strip()
        if not text:
            text = fact or "我先停在这里。你可以继续说明想试听的目标和时间区间。"
        return text[:4000], _refs(collected)

    def _context(self, task_id: str, selected: list[str]) -> dict:
        task = self.service.get_task(task_id)
        variants = []
        for variant in task["variants"]:
            variants.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "reason": variant["reason"],
                    "summary": variant["spec"].get("summary"),
                    "model_name": variant["spec"].get("model_name"),
                    "output_target": variant["spec"].get("output_target"),
                    "params": variant["spec"].get("params"),
                    "jobs": [
                        {
                            "id": job["id"],
                            "kind": job["kind"],
                            "status": job["status"],
                            "stage": job["stage"],
                            "progress": job["progress"],
                            "error": job["error"],
                            "note": job["note"],
                            "start_sec": job["start_sec"],
                            "end_sec": job["end_sec"],
                        }
                        for job in variant["jobs"]
                    ],
                }
            )
        hardware = self.hardware.snapshot() if self.hardware else None
        return {
            "task": {
                "id": task["id"],
                "title": task["title"],
                "filename": task["filename"],
                "duration_sec": task["duration_sec"],
                "sample_rate": task["sample_rate"],
                "channels": task["channels"],
                "goal": task["goal"],
                "draft": task["draft"],
                "selected_variant_id": task["selected_variant_id"],
                "status": task["status"],
            },
            "variants": variants,
            "selected_task_ids": selected,
            "presets": [
                {
                    "id": preset["id"],
                    "arch": preset["arch"],
                    "model_name": preset["model_name"],
                    "output_target": preset["output_target"],
                    "params": preset["params"],
                    "summary": preset["summary"],
                    "use": preset["use"],
                    "when": preset["when"],
                }
                for preset in load_presets()
            ],
            "executable_targets": TARGETS,
            "hardware": hardware,
        }

    def _call(self, task_id: str, message_id: str, name: str, arguments: dict, selected: list[str]) -> dict:
        try:
            if name == "inspect_task":
                return {"ok": True, "task": self._context(task_id, selected)}
            if name == "list_models":
                models = self.catalog.list_models(
                    arch=arguments.get("arch") or None,
                    query=arguments.get("query") or "",
                    installed=arguments.get("installed") or None,
                )
                return {"ok": True, "models": models[:40], "presets": load_presets()}
            if name == "download_model":
                arch = arguments.get("arch")
                model_name = arguments.get("model_name")
                if not self.catalog.is_known(arch, model_name):
                    raise ServiceError("只能下载官方目录里的模型")
                job = self.service.downloads.enqueue(
                    arch,
                    model_name,
                    _request_key(message_id, name, {"arch": arch, "model_name": model_name}),
                )
                return {"ok": True, "download": {"id": job["id"], "status": job["status"], "model_name": model_name, "arch": arch}}
            if name == "create_preview":
                draft = {
                    "arch": arguments.get("arch"),
                    "model_name": arguments.get("model_name"),
                    "output_target": arguments.get("output_target"),
                    "params": arguments.get("params") or {},
                    "start_sec": arguments.get("start_sec", 0),
                    "end_sec": arguments.get("end_sec", 30),
                }
                job = self.service.create_preview(
                    task_id,
                    draft,
                    _request_key(message_id, name, draft),
                    "agent",
                    str(arguments.get("reason") or "按反馈提交新的试听"),
                )
                return {"ok": True, "job": job}
            if name == "select_variant":
                task = self.service.select_variant(task_id, arguments.get("variant_id"))
                return {"ok": True, "selected_variant_id": task["selected_variant_id"]}
            if name == "run_full":
                jobs = self.service.run_full(
                    task_id,
                    arguments.get("variant_id") or None,
                    arguments.get("target_task_ids") or None,
                    _request_key(message_id, name, arguments),
                    "agent",
                    selected,
                    str(arguments.get("reason") or "处理整首"),
                )
                return {"ok": True, "jobs": jobs}
            if name == "cancel_job":
                job = self.service.cancel_job(arguments.get("job_id"))
                return {"ok": True, "job": job}
            return {"ok": False, "error": "没有这个工具"}
        except ServiceError as exc:
            return {"ok": False, "error": exc.message}
        except Exception as exc:
            return {"ok": False, "error": f"工具执行失败：{exc}"}


def _system_prompt() -> str:
    return (
        "你是 UVR 本地音频分离工作台里的单个助手。你只能通过工具读取真实任务和模型，并提交真实任务。"
        "不要声称自己听过音频，不要编造残留、失真、分数或听感。"
        "默认只提交一版试听。用户明确要求调整、比较、换模型或说残留以后，才提交另一个不同模型或不同有效预设。"
        "batch size 只影响速度和显存，不能当作音质档位。音质相关的可调项是 MDX overlap、VR aggression、Demucs shifts。"
        "用户只说先选方案时，只调用 select_variant。用户明确说处理整首、全曲或整曲时，调用 run_full，不要再追问确认。"
        "用户说直接处理整首时可以不试听。"
        "用户说副歌但没有起止时间时，先问一次起止秒数，不要猜。"
        "试听默认 0 到 30 秒；文件更短就用全长。"
        "批量时只能把上下文里的 selected_task_ids 原样传给 run_full。没有明确选中的文件时，先问，不要扫描磁盘。"
        "推荐模型只能来自 presets 或 list_models 的返回。提交后就停止，等真实任务结果或用户的下一步。"
        "回复用简短中文，说明准备用的模型和参数，以及不能保证新方案一定更好。"
    )


def _tools() -> list[dict]:
    spec_props = {
        "arch": {"type": "string", "enum": ["mdx", "vr", "demucs"]},
        "model_name": {"type": "string"},
        "output_target": {"type": "string"},
        "params": {"type": "object"},
        "start_sec": {"type": "number"},
        "end_sec": {"type": "number"},
        "reason": {"type": "string"},
    }
    return [
        _tool("inspect_task", "读取当前任务、方案、执行状态和错误。", {}),
        _tool("list_models", "查询官方模型目录、安装状态和预设。", {"arch": {"type": "string"}, "query": {"type": "string"}, "installed": {"type": "string"}}),
        _tool("download_model", "下载一个指定的官方模型。", {"arch": {"type": "string"}, "model_name": {"type": "string"}}, ["arch", "model_name"]),
        _tool("create_preview", "创建一个方案并提交一次试听。", spec_props, ["arch", "model_name", "output_target", "reason"]),
        _tool("select_variant", "保存用户选中的方案，不处理整首。", {"variant_id": {"type": "string"}}, ["variant_id"]),
        _tool("run_full", "处理整首。批量时传入已选任务 id。", {"variant_id": {"type": "string"}, "target_task_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}),
        _tool("cancel_job", "取消排队或正在运行的任务。", {"job_id": {"type": "string"}}, ["job_id"]),
    ]


def _tool(name: str, description: str, properties: dict, required: list | None = None) -> dict:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}


def _parse_call(call: dict) -> tuple[str, dict]:
    function = call.get("function") or {}
    name = function.get("name") or call.get("name") or ""
    raw = function.get("arguments") or call.get("arguments") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return name, raw


def _request_key(message_id: str, name: str, arguments: dict) -> str:
    raw = json.dumps({"m": message_id, "t": name, "a": arguments}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _summarize(results: list[dict]) -> str:
    lines = []
    for item in results:
        if not item.get("ok"):
            if item.get("error"):
                lines.append(item["error"])
            continue
        if item.get("name") == "create_preview" and item.get("job"):
            lines.append(f"已提交试听：{item['job'].get('summary') or item['job'].get('model_name')}")
        elif item.get("name") == "run_full" and item.get("jobs"):
            lines.append("已提交 " + "、".join(f"整首 {job.get('summary') or job.get('model_name')}" for job in item["jobs"]))
        elif item.get("name") == "select_variant":
            lines.append("已保存当前方案，还没有处理整首。")
        elif item.get("name") == "cancel_job":
            lines.append("已取消这个任务。")
        elif item.get("name") == "download_model":
            lines.append(f"已提交模型下载：{item.get('download', {}).get('model_name')}")
    return "\n".join(lines)


def _refs(results: list[dict]) -> list[dict]:
    refs = []
    for item in results:
        jobs = []
        if item.get("job"):
            jobs.append(item["job"])
        jobs.extend(item.get("jobs") or [])
        for job in jobs:
            refs.append({"type": "job", "id": job["id"], "variant_id": job.get("variant_id"), "task_id": job.get("task_id")})
    return refs


def _clean_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _openai_complete(settings, messages: list[dict], tools: list[dict]) -> dict:
    if not settings.llm_configured:
        raise LLMError("还没有配置语言模型。")
    payload = {"model": settings.llm_model, "messages": messages, "tools": tools, "temperature": 0.2}
    request = urllib.request.Request(
        settings.llm_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"语言模型接口返回 {exc.code}。已提交的音频任务没有被改动。{detail}") from exc
    except Exception as exc:
        raise LLMError(f"语言模型没有响应。已提交的音频任务没有被改动。{exc}") from exc
    try:
        return body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("语言模型返回了无法读取的结果。已提交的音频任务没有被改动。") from exc
