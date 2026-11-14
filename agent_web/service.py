"""The only task pipeline used by the workbench and the agent."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
import time
from pathlib import Path

from agent_web.argv import build_argv
from agent_web.audio_util import AudioError, probe
from agent_web.executor import explain_failure
from agent_web.intent import message_requests_adjustment, message_requests_full
from agent_web.spec import SpecError, default_draft, draft_to_spec, dumps, preview_range, quality_signature, spec_key
from agent_web.util import new_id, now_iso

log = logging.getLogger("uvr.agent")

ACTIVE_STATUSES = ("queued", "running")
REUSABLE_STATUSES = ("queued", "running", "succeeded")


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class TaskService:
    def __init__(self, settings, database, catalog, executor, downloads, hardware=None):
        self.settings = settings
        self.db = database
        self.catalog = catalog
        self.executor = executor
        self.downloads = downloads
        self.hardware = hardware
        self.shutting_down = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.shutting_down = False
        self._thread = threading.Thread(target=self._loop, name="uvr-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutting_down = True
        self._stop.set()
        self.executor.shutdown()
        for _ in range(50):
            if not self.executor.busy():
                break
            time.sleep(0.1)
        self.downloads.stop()

    def recover_after_restart(self) -> None:
        stamp = now_iso()
        with self.db.transaction() as tx:
            tx.execute(
                """
                UPDATE jobs
                SET status='interrupted', stage='interrupted',
                    error='服务重启，运行已中断。可以重试。', updated_at=?
                WHERE status='running'
                """,
                (stamp,),
            )
            tx.execute(
                """
                UPDATE jobs
                SET hold=1, stage='paused',
                    note='服务重启，排队已暂停。点继续后才会开始。', updated_at=?
                WHERE status='queued' AND hold=0
                """,
                (stamp,),
            )

    def create_task(self, source: Path, filename: str | None = None) -> dict:
        source = Path(source)
        meta = probe(source)
        task_id = new_id()
        folder = self.settings.data_dir / "uploads" / task_id
        folder.mkdir(parents=True, exist_ok=True)
        stored = folder / _safe_name(filename or source.name)
        shutil.copy2(source, stored)
        draft = default_draft(meta["duration_sec"])
        title = Path(filename or source.name).stem or "未命名"
        stamp = now_iso()
        with self.db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO tasks
                (id, title, filename, stored_path, duration_sec, sample_rate, channels, goal, draft_json, selected_variant_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, NULL, ?)
                """,
                (
                    task_id,
                    title[:180],
                    stored.name,
                    str(stored),
                    meta["duration_sec"],
                    meta["sample_rate"],
                    meta["channels"],
                    dumps(draft),
                    stamp,
                ),
            )
        return self.get_task(task_id)

    def list_tasks(self, scope: str = "all") -> list[dict]:
        with self.db.transaction() as tx:
            rows = tx.query("SELECT * FROM tasks ORDER BY created_at DESC")
            jobs = tx.query("SELECT * FROM jobs ORDER BY created_at ASC")
        by_task: dict[str, list] = {}
        for job in jobs:
            by_task.setdefault(job["task_id"], []).append(job)
        items = []
        for row in rows:
            headline = _headline(by_task.get(row["id"], []))
            if scope == "active" and headline["state"] not in {"running", "queued", "waiting_model", "paused", "blocked"}:
                continue
            if scope == "done" and headline["state"] != "succeeded":
                continue
            items.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "filename": row["filename"],
                    "duration_sec": row["duration_sec"],
                    "goal": row["goal"] or "",
                    "created_at": row["created_at"],
                    "selected_variant_id": row["selected_variant_id"],
                    "status": headline,
                }
            )
        return items

    def get_task(self, task_id: str) -> dict:
        with self.db.transaction() as tx:
            return self._snapshot(tx, task_id)

    def update_draft(self, task_id: str, patch: dict) -> dict:
        self._warm_catalog()
        with self.db.transaction() as tx:
            task = self._task_row(tx, task_id)
            current = json.loads(task["draft_json"])
            merged = {**current, **(patch or {})}
            if "params" in (patch or {}):
                merged["params"] = {**(current.get("params") or {}), **(patch.get("params") or {})}
            try:
                spec = draft_to_spec(merged)
                start, end = preview_range(task["duration_sec"], merged)
            except SpecError as exc:
                raise ServiceError(str(exc)) from exc
            self._require_known(spec)
            stored = {**spec, "start_sec": start, "end_sec": end}
            tx.execute("UPDATE tasks SET draft_json=? WHERE id=?", (dumps(stored), task_id))
        return self.get_task(task_id)

    def create_preview(self, task_id: str, draft: dict | None, request_key: str | None, source: str, reason: str) -> dict:
        key = _clean_key(request_key)
        self._warm_catalog()
        with self.db.transaction() as tx:
            task = self._task_row(tx, task_id)
            merged = json.loads(task["draft_json"])
            if draft:
                merged.update(draft)
                if "params" in draft:
                    merged["params"] = {**(json.loads(task["draft_json"]).get("params") or {}), **(draft.get("params") or {})}
            try:
                spec = draft_to_spec(merged)
                start, end = preview_range(task["duration_sec"], merged)
            except SpecError as exc:
                raise ServiceError(str(exc)) from exc
            self._require_known(spec)
            if key:
                existing = tx.one("SELECT * FROM jobs WHERE request_key=?", (key,))
                if existing:
                    return self._job_public(tx, existing)
            succeeded = tx.query(
                "SELECT * FROM jobs WHERE task_id=? AND kind='preview' AND status='succeeded' ORDER BY created_at",
                (task_id,),
            )
            if source == "agent" and succeeded:
                message = self._last_user_text(tx, task_id)
                if not message_requests_adjustment(message):
                    raise ServiceError("已经有一版试听。要新方案，需要你明确提出调整或比较。")
            for job in succeeded:
                old = json.loads(job["spec_json"])
                if quality_signature(old) == quality_signature(spec) and old["params"].get("batch_size") != spec["params"].get("batch_size"):
                    raise ServiceError("batch size 只影响速度和显存，不能当成新的音质方案。")
            identity = spec_key(task_id, "preview", spec, start, end)
            reusable = tx.one(
                f"SELECT * FROM jobs WHERE spec_key=? AND status IN ({_marks(REUSABLE_STATUSES)}) ORDER BY created_at LIMIT 1",
                (identity, *REUSABLE_STATUSES),
            )
            if reusable:
                if reusable["hold"]:
                    tx.execute(
                        "UPDATE jobs SET hold=0, stage='queued', note='', updated_at=? WHERE id=?",
                        (now_iso(), reusable["id"]),
                    )
                tx.execute(
                    "UPDATE tasks SET selected_variant_id=?, draft_json=? WHERE id=?",
                    (reusable["variant_id"], dumps({**spec, "start_sec": start, "end_sec": end}), task_id),
                )
                return self._job_public(tx, tx.one("SELECT * FROM jobs WHERE id=?", (reusable["id"],)))
            variant = self._ensure_variant(tx, task_id, spec, reason or ("手动提交试听" if source == "manual" else "提交试听"))
            job = self._insert_job(
                tx,
                task_id=task_id,
                variant_id=variant["id"],
                kind="preview",
                start=start,
                end=end,
                spec=spec,
                identity=identity,
                request_key=key,
            )
            tx.execute(
                "UPDATE tasks SET selected_variant_id=?, draft_json=? WHERE id=?",
                (variant["id"], dumps({**spec, "start_sec": start, "end_sec": end}), task_id),
            )
            return self._job_public(tx, job)

    def select_variant(self, task_id: str, variant_id: str) -> dict:
        with self.db.transaction() as tx:
            task = self._task_row(tx, task_id)
            variant = self._variant_row(tx, variant_id)
            if variant["task_id"] != task_id:
                raise ServiceError("方案不属于这个任务", 404)
            spec = json.loads(variant["spec_json"])
            preview = tx.one(
                """
                SELECT * FROM jobs
                WHERE variant_id=? AND kind='preview'
                ORDER BY created_at DESC LIMIT 1
                """,
                (variant_id,),
            )
            draft = json.loads(task["draft_json"])
            start = preview["start_sec"] if preview and preview["start_sec"] is not None else draft.get("start_sec", 0)
            end = preview["end_sec"] if preview and preview["end_sec"] is not None else draft.get("end_sec", 30)
            tx.execute(
                "UPDATE tasks SET selected_variant_id=?, draft_json=? WHERE id=?",
                (variant_id, dumps({**spec, "start_sec": start, "end_sec": end}), task_id),
            )
        return self.get_task(task_id)

    def run_full(
        self,
        task_id: str,
        variant_id: str | None,
        target_task_ids: list[str] | None,
        request_key: str | None,
        source: str,
        allowed_task_ids: list[str] | None,
        reason: str,
    ) -> list[dict]:
        key = _clean_key(request_key)
        self._warm_catalog()
        targets = target_task_ids or [task_id]
        if not targets:
            raise ServiceError("没有选中要处理的文件")
        if len(targets) > 20:
            raise ServiceError("一次最多处理 20 个已上传文件")
        with self.db.transaction() as tx:
            task = self._task_row(tx, task_id)
            if source == "agent" and not message_requests_full(self._last_user_text(tx, task_id)):
                raise ServiceError("还没有明确的整首处理意图。说处理整首就会开始，不会再确认一次。")
            if source == "agent":
                allowed = set(allowed_task_ids or [task_id])
                if not set(targets) <= allowed:
                    raise ServiceError("批量目标必须是当前已经选中的任务")
            try:
                spec, source_variant = self._resolve_full_spec(tx, task, variant_id)
            except SpecError as exc:
                raise ServiceError(str(exc)) from exc
            self._require_known(spec)
            jobs = []
            for target_id in targets:
                self._task_row(tx, target_id)
                child = None if not key else hashlib.sha256(f"{key}:{target_id}".encode("utf-8")).hexdigest()[:32]
                if child:
                    existing = tx.one("SELECT * FROM jobs WHERE request_key=?", (child,))
                    if existing:
                        jobs.append(self._job_public(tx, existing))
                        continue
                variant = source_variant if target_id == task_id and source_variant else None
                if variant is None:
                    variant = self._ensure_variant(tx, target_id, spec, reason or "复用当前方案")
                identity = spec_key(target_id, "full", spec, None, None)
                reusable = tx.one(
                    f"SELECT * FROM jobs WHERE spec_key=? AND status IN ({_marks(REUSABLE_STATUSES)}) ORDER BY created_at LIMIT 1",
                    (identity, *REUSABLE_STATUSES),
                )
                if reusable:
                    if reusable["hold"]:
                        tx.execute(
                            "UPDATE jobs SET hold=0, stage='queued', note='', updated_at=? WHERE id=?",
                            (now_iso(), reusable["id"]),
                        )
                    jobs.append(self._job_public(tx, tx.one("SELECT * FROM jobs WHERE id=?", (reusable["id"],))))
                    continue
                job = self._insert_job(
                    tx,
                    task_id=target_id,
                    variant_id=variant["id"],
                    kind="full",
                    start=None,
                    end=None,
                    spec=spec,
                    identity=identity,
                    request_key=child,
                )
                if target_id == task_id:
                    tx.execute("UPDATE tasks SET selected_variant_id=? WHERE id=?", (variant["id"], task_id))
                jobs.append(self._job_public(tx, job))
            return jobs

    def cancel_job(self, job_id: str) -> dict:
        with self.db.transaction() as tx:
            job = self._job_row(tx, job_id)
            if job["status"] == "queued":
                tx.execute(
                    "UPDATE jobs SET status='cancelled', stage='cancelled', note='已取消', updated_at=? WHERE id=?",
                    (now_iso(), job_id),
                )
                return self._job_public(tx, tx.one("SELECT * FROM jobs WHERE id=?", (job_id,)))
            if job["status"] != "running":
                raise ServiceError("这个任务已经结束")
            tx.execute(
                "UPDATE jobs SET cancel_requested=1, stage='cancelling', updated_at=? WHERE id=?",
                (now_iso(), job_id),
            )
        self.executor.cancel(job_id)
        return self.job(job_id)

    def retry_job(self, job_id: str) -> dict:
        with self.db.transaction() as tx:
            job = self._job_row(tx, job_id)
            if job["status"] not in ("failed", "cancelled", "interrupted"):
                raise ServiceError("只有失败、取消或中断的任务可以重试")
            spec = json.loads(job["spec_json"])
            created = self._insert_job(
                tx,
                task_id=job["task_id"],
                variant_id=job["variant_id"],
                kind=job["kind"],
                start=job["start_sec"],
                end=job["end_sec"],
                spec=spec,
                identity=job["spec_key"],
                request_key=None,
            )
            return self._job_public(tx, created)

    def continue_job(self, job_id: str) -> dict:
        with self.db.transaction() as tx:
            job = self._job_row(tx, job_id)
            if job["status"] != "queued" or not job["hold"]:
                raise ServiceError("这个任务不在暂停的队列里")
            tx.execute(
                "UPDATE jobs SET hold=0, stage='queued', note='', updated_at=? WHERE id=?",
                (now_iso(), job_id),
            )
            return self._job_public(tx, tx.one("SELECT * FROM jobs WHERE id=?", (job_id,)))

    def job(self, job_id: str) -> dict:
        with self.db.transaction() as tx:
            return self._job_public(tx, self._job_row(tx, job_id))

    def add_message(self, task_id: str, role: str, content: str, refs: list | None = None) -> dict:
        text = (content or "").strip()
        if not text:
            raise ServiceError("消息是空的")
        if len(text) > 8000:
            raise ServiceError("消息太长")
        if role not in ("user", "assistant"):
            raise ServiceError("消息角色无效")
        stamp = now_iso()
        message_id = new_id()
        with self.db.transaction() as tx:
            self._task_row(tx, task_id)
            tx.execute(
                "INSERT INTO messages (id, task_id, role, content, refs_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, task_id, role, text, dumps(refs or []), stamp),
            )
            if role == "user":
                goal = _goal_from_text(text)
                if goal:
                    tx.execute("UPDATE tasks SET goal=? WHERE id=?", (goal, task_id))
        return {"id": message_id, "role": role, "content": text, "refs": refs or [], "created_at": stamp}

    def list_messages(self, task_id: str) -> list[dict]:
        with self.db.transaction() as tx:
            self._task_row(tx, task_id)
            rows = tx.query(
                "SELECT * FROM messages WHERE task_id=? ORDER BY created_at ASC LIMIT 200",
                (task_id,),
            )
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "refs": json.loads(row["refs_json"] or "[]"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_downloads(self) -> list[dict]:
        with self.db.transaction() as tx:
            rows = tx.query("SELECT * FROM download_jobs ORDER BY created_at DESC LIMIT 40")
        return [_download_public(row) for row in rows]

    def task_audio(self, task_id: str) -> Path:
        with self.db.transaction() as tx:
            task = self._task_row(tx, task_id)
        return self._guard(Path(task["stored_path"]))

    def artifact_audio(self, artifact_id: str) -> tuple[Path, str]:
        with self.db.transaction() as tx:
            row = tx.one("SELECT * FROM artifacts WHERE id=?", (artifact_id,))
        if not row:
            raise ServiceError("找不到音频", 404)
        return self._guard(Path(row["path"])), row["label"]

    def tick(self) -> None:
        if self.shutting_down or self.executor.busy():
            return
        with self.db.transaction() as tx:
            rows = [dict(row) for row in tx.query(
                "SELECT * FROM jobs WHERE status='queued' AND hold=0 ORDER BY created_at ASC"
            )]
        if not rows:
            return
        if any(row["stage"] == "blocked" for row in rows) and not self.executor.leftover_blocking():
            with self.db.transaction() as tx:
                tx.execute(
                    "UPDATE jobs SET stage='queued', note='', updated_at=? WHERE status='queued' AND stage='blocked'",
                    (now_iso(),),
                )
            return
        chosen = None
        for row in rows:
            if row["stage"] in ("waiting_model", "blocked"):
                continue
            spec = json.loads(row["spec_json"])
            if self.catalog.is_installed(spec["arch"], spec["model_name"]):
                chosen = row
                break
            with self.db.transaction() as tx:
                current = tx.one("SELECT status, stage FROM jobs WHERE id=?", (row["id"],))
                if current and current["status"] == "queued" and current["stage"] != "waiting_model":
                    tx.execute(
                        "UPDATE jobs SET stage='waiting_model', note='等待模型下载', updated_at=? WHERE id=?",
                        (now_iso(), row["id"]),
                    )
            self.downloads.enqueue(spec["arch"], spec["model_name"])
        if not chosen:
            return
        if self.executor.leftover_blocking():
            with self.db.transaction() as tx:
                tx.execute(
                    "UPDATE jobs SET stage='blocked', note='检测到上次的推理进程仍在运行，新的推理先暂停。', updated_at=? WHERE id=?",
                    (now_iso(), chosen["id"]),
                )
            return
        spec = json.loads(chosen["spec_json"])
        with self.db.transaction() as tx:
            current = tx.one("SELECT * FROM jobs WHERE id=?", (chosen["id"],))
            if not current or current["status"] != "queued" or current["hold"]:
                return
            task = self._task_row(tx, current["task_id"])
            output = self.settings.data_dir / "jobs" / current["id"]
            tx.execute(
                "UPDATE jobs SET status='running', stage='preparing', output_dir=?, updated_at=? WHERE id=?",
                (str(output), now_iso(), current["id"]),
            )
            current = tx.one("SELECT * FROM jobs WHERE id=?", (current["id"],))
        self._launch(dict(current), dict(task), spec)

    def on_download_finished(self, arch: str, name: str, ok: bool, message: str) -> None:
        self.catalog.invalidate()
        with self.db.transaction() as tx:
            rows = tx.query("SELECT * FROM jobs WHERE status='queued' AND stage='waiting_model'")
            for row in rows:
                spec = json.loads(row["spec_json"])
                if spec["arch"] != arch or spec["model_name"] != name:
                    continue
                if ok:
                    tx.execute(
                        "UPDATE jobs SET stage='queued', note='', updated_at=? WHERE id=?",
                        (now_iso(), row["id"]),
                    )
                else:
                    tx.execute(
                        """
                        UPDATE jobs
                        SET status='failed', stage='failed', error=?, updated_at=?
                        WHERE id=?
                        """,
                        (f"模型下载失败：{message}"[:800], now_iso(), row["id"]),
                    )

    def on_progress(self, job_id: str, stage: str | None, progress: float | None) -> None:
        with self.db.transaction() as tx:
            job = tx.one("SELECT status, cancel_requested FROM jobs WHERE id=?", (job_id,))
            if not job or job["status"] != "running" or job["cancel_requested"]:
                return
            tx.execute(
                "UPDATE jobs SET stage=COALESCE(?, stage), progress=COALESCE(?, progress), updated_at=? WHERE id=?",
                (stage, progress, now_iso(), job_id),
            )

    def on_exit(self, job_id: str, code: int, outputs: list[Path], tail: str) -> None:
        with self.db.transaction() as tx:
            job = tx.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if not job or job["status"] not in ("running", "queued"):
                return
            stamp = now_iso()
            if self.shutting_down:
                tx.execute(
                    """
                    UPDATE jobs
                    SET status='interrupted', stage='interrupted',
                        error='服务已停止，运行已中断。可以重试。', updated_at=?
                    WHERE id=?
                    """,
                    (stamp, job_id),
                )
                return
            if job["cancel_requested"]:
                tx.execute(
                    "UPDATE jobs SET status='cancelled', stage='cancelled', note='已取消', error='', updated_at=? WHERE id=?",
                    (stamp, job_id),
                )
                return
            if code != 0:
                tx.execute(
                    "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=?",
                    (explain_failure(tail, code)[:800], stamp, job_id),
                )
                return
            try:
                rows = _validated_outputs(job, outputs)
            except AudioError as exc:
                tx.execute(
                    "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=?",
                    (str(exc)[:800], stamp, job_id),
                )
                return
            for role, label, path, meta in rows:
                tx.execute(
                    """
                    INSERT INTO artifacts
                    (id, job_id, role, label, path, duration_sec, sample_rate, channels, format)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id(),
                        job_id,
                        role,
                        label,
                        str(path),
                        meta["duration_sec"],
                        meta["sample_rate"],
                        meta["channels"],
                        meta["format"],
                    ),
                )
            tx.execute(
                """
                UPDATE jobs
                SET status='succeeded', stage='complete', progress=100, error='', note='', updated_at=?
                WHERE id=?
                """,
                (stamp, job_id),
            )

    def _launch(self, job: dict, task: dict, spec: dict) -> None:
        try:
            output = Path(job["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            if job["kind"] == "preview":
                input_path = output / "source_clip.wav"
            else:
                input_path = Path(task["stored_path"])
            device = self._device()
            argv = build_argv(self.settings.inference_python, self.settings.repo_root, spec, device, input_path, output)
            self.executor.start(
                job,
                task,
                argv,
                self.settings.repo_root,
                self.on_progress,
                self.on_exit,
                lambda: self._cancel_requested(job["id"]),
            )
        except Exception as exc:
            log.exception("failed to start worker")
            with self.db.transaction() as tx:
                tx.execute(
                    "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=? AND status='running'",
                    (str(exc)[:800], now_iso(), job["id"]),
                )

    def _device(self) -> str:
        if self.settings.device == "gpu":
            return "gpu"
        if self.settings.device == "cpu":
            return "cpu"
        if self.hardware and self.hardware.has_nvidia():
            return "gpu"
        return "cpu"

    def _cancel_requested(self, job_id: str) -> bool:
        with self.db.transaction() as tx:
            row = tx.one("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,))
        return bool(row and row["cancel_requested"])

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("queue tick failed")
            self._stop.wait(0.4)

    def _warm_catalog(self) -> None:
        refresh = getattr(self.catalog, "refresh", None)
        if not refresh:
            return
        try:
            refresh()
        except Exception:
            return

    def _require_known(self, spec: dict) -> None:
        if not self.catalog.is_known(spec["arch"], spec["model_name"]):
            raise ServiceError("模型不在官方目录里，也不能使用未登记的名称")

    def _snapshot(self, tx, task_id: str) -> dict:
        task = self._task_row(tx, task_id)
        variants = tx.query("SELECT * FROM variants WHERE task_id=? ORDER BY created_at ASC", (task_id,))
        jobs = tx.query("SELECT * FROM jobs WHERE task_id=? ORDER BY created_at ASC", (task_id,))
        artifacts = []
        if jobs:
            marks = ",".join("?" for _ in jobs)
            artifacts = tx.query(
                f"SELECT * FROM artifacts WHERE job_id IN ({marks}) ORDER BY label",
                tuple(job["id"] for job in jobs),
            )
        by_job: dict[str, list] = {}
        for artifact in artifacts:
            by_job.setdefault(artifact["job_id"], []).append(_artifact_public(artifact))
        by_variant: dict[str, list] = {}
        for job in jobs:
            by_variant.setdefault(job["variant_id"], []).append(self._job_public(tx, job, by_job.get(job["id"], [])))
        public_variants = []
        for index, variant in enumerate(variants, start=1):
            spec = json.loads(variant["spec_json"])
            public_variants.append(
                {
                    "id": variant["id"],
                    "label": f"方案 {index}",
                    "stored_label": variant["label"],
                    "spec": spec,
                    "reason": variant["reason"],
                    "created_at": variant["created_at"],
                    "jobs": by_variant.get(variant["id"], []),
                }
            )
        return {
            "id": task["id"],
            "title": task["title"],
            "filename": task["filename"],
            "duration_sec": task["duration_sec"],
            "sample_rate": task["sample_rate"],
            "channels": task["channels"],
            "goal": task["goal"] or "",
            "draft": json.loads(task["draft_json"]),
            "selected_variant_id": task["selected_variant_id"],
            "created_at": task["created_at"],
            "status": _headline(jobs),
            "variants": public_variants,
        }

    def _ensure_variant(self, tx, task_id: str, spec: dict, reason: str) -> dict:
        encoded = dumps(spec)
        found = tx.one("SELECT * FROM variants WHERE task_id=? AND spec_json=?", (task_id, encoded))
        if found:
            return found
        count = tx.one("SELECT COUNT(*) AS n FROM variants WHERE task_id=?", (task_id,))["n"]
        variant_id = new_id()
        tx.execute(
            "INSERT INTO variants (id, task_id, label, spec_json, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (variant_id, task_id, f"方案 {count + 1}", encoded, (reason or "提交方案")[:400], now_iso()),
        )
        return tx.one("SELECT * FROM variants WHERE id=?", (variant_id,))

    def _resolve_full_spec(self, tx, task, variant_id: str | None):
        draft = json.loads(task["draft_json"])
        spec = draft_to_spec(draft)
        if variant_id:
            variant = self._variant_row(tx, variant_id)
            if variant["task_id"] != task["id"]:
                raise ServiceError("方案不属于这个任务", 404)
            return json.loads(variant["spec_json"]), variant
        if task["selected_variant_id"]:
            selected = self._variant_row(tx, task["selected_variant_id"])
            selected_spec = json.loads(selected["spec_json"])
            if dumps(selected_spec) == dumps(spec):
                return selected_spec, selected
        return spec, None

    def _insert_job(self, tx, task_id, variant_id, kind, start, end, spec, identity, request_key):
        job_id = new_id()
        stamp = now_iso()
        tx.execute(
            """
            INSERT INTO jobs
            (id, task_id, variant_id, kind, start_sec, end_sec, status, stage, progress, error, note,
             output_dir, request_key, spec_key, spec_json, hold, cancel_requested, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', NULL, '', '', '', ?, ?, ?, 0, 0, ?, ?)
            """,
            (job_id, task_id, variant_id, kind, start, end, request_key, identity, dumps(spec), stamp, stamp),
        )
        return tx.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def _job_public(self, tx, job, artifacts: list | None = None) -> dict:
        if artifacts is None:
            artifacts = [_artifact_public(row) for row in tx.query("SELECT * FROM artifacts WHERE job_id=? ORDER BY label", (job["id"],))]
        spec = json.loads(job["spec_json"])
        return {
            "id": job["id"],
            "task_id": job["task_id"],
            "variant_id": job["variant_id"],
            "kind": job["kind"],
            "status": job["status"],
            "stage": job["stage"] or "",
            "progress": job["progress"],
            "error": job["error"] or "",
            "note": job["note"] or "",
            "hold": bool(job["hold"]),
            "start_sec": job["start_sec"],
            "end_sec": job["end_sec"],
            "model_name": spec.get("model_name"),
            "summary": spec.get("summary"),
            "spec": spec,
            "artifacts": artifacts,
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

    def _task_row(self, tx, task_id: str):
        row = tx.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not row:
            raise ServiceError("找不到任务", 404)
        return row

    def _variant_row(self, tx, variant_id: str):
        row = tx.one("SELECT * FROM variants WHERE id=?", (variant_id,))
        if not row:
            raise ServiceError("找不到方案", 404)
        return row

    def _job_row(self, tx, job_id: str):
        row = tx.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise ServiceError("找不到执行记录", 404)
        return row

    def _last_user_text(self, tx, task_id: str) -> str:
        row = tx.one(
            "SELECT content FROM messages WHERE task_id=? AND role='user' ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        return row["content"] if row else ""

    def _guard(self, path: Path) -> Path:
        resolved = path.resolve()
        root = self.settings.data_dir.resolve()
        if resolved != root and root not in resolved.parents:
            raise ServiceError("音频路径无效", 404)
        if not resolved.is_file():
            raise ServiceError("音频不存在", 404)
        return resolved


def _clean_key(value: str | None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", text):
        raise ServiceError("请求标识无效")
    return text


def _marks(values: tuple[str, ...]) -> str:
    return ",".join("?" for _ in values)


def _safe_name(name: str) -> str:
    base = Path(name or "audio.wav").name
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in base).strip()
    return (cleaned or "audio.wav")[:120]


def _goal_from_text(text: str) -> str:
    if any(token in text for token in ("伴奏", "去人声", "卡拉")):
        return "instrumental"
    if any(token in text for token in ("人声", "干声")):
        return "vocals"
    return ""


def _headline(jobs) -> dict:
    if not jobs:
        return {"state": "empty", "progress": None, "stage": "", "error": "", "note": "", "kind": "", "job_id": ""}
    running = [job for job in jobs if job["status"] == "running"]
    job = running[-1] if running else jobs[-1]
    state = job["status"]
    if state == "queued":
        if job["hold"]:
            state = "paused"
        elif job["stage"] == "waiting_model":
            state = "waiting_model"
        elif job["stage"] == "blocked":
            state = "blocked"
        else:
            state = "queued"
    return {
        "state": state,
        "progress": job["progress"],
        "stage": job["stage"] or "",
        "error": job["error"] or "",
        "note": job["note"] or "",
        "kind": job["kind"],
        "job_id": job["id"],
    }


def _artifact_public(row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "label": row["label"],
        "duration_sec": row["duration_sec"],
        "sample_rate": row["sample_rate"],
        "channels": row["channels"],
        "format": row["format"],
    }


def _download_public(row) -> dict:
    return {
        "id": row["id"],
        "model_name": row["model_name"],
        "arch": row["arch"],
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"] or "",
        "error": row["error"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _validated_outputs(job, outputs: list[Path]) -> list[tuple]:
    rows = []
    folder = Path(job["output_dir"] or "")
    clip = folder / "source_clip.wav"
    if clip.is_file():
        meta = probe(clip)
        if meta["duration_sec"] <= 0:
            raise AudioError("试听原音片段无法读取")
        rows.append(("source_clip", "原音片段", clip, meta))
    stems = []
    for path in outputs:
        meta = probe(Path(path))
        if meta["duration_sec"] <= 0 or meta["sample_rate"] <= 0 or meta["channels"] <= 0:
            raise AudioError(f"产物无法读取：{Path(path).name}")
        stems.append(("stem", _stem_label(Path(path)), Path(path), meta))
    if not stems:
        raise AudioError("没有找到可读的分离结果")
    return rows + stems


def _stem_label(path: Path) -> str:
    name = path.stem
    if "(" in name and name.endswith(")"):
        return name[name.rfind("(") + 1 : -1]
    return name
