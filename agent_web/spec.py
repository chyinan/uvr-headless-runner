"""Canonical separation specs. Invalid combinations stop before a worker starts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PRESET_PATH = Path(__file__).with_name("presets.json")

WAV_TYPES = ("PCM_16", "PCM_24")
ARCHES = ("mdx", "vr", "demucs")

TARGETS = {
    "mdx": ("instrumental", "vocals", "all"),
    "vr": ("instrumental", "vocals", "all"),
    "demucs": ("vocals", "drums", "bass", "other", "all"),
}


class SpecError(ValueError):
    pass


def load_presets() -> list[dict[str, Any]]:
    with PRESET_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not data:
        raise SpecError("预设配置为空")
    return data


def default_preset() -> dict[str, Any]:
    return load_presets()[0]


STEM_ID = {
    "Vocals": "vocals",
    "Instrumental": "instrumental",
    "Other": "other",
    "Bass": "bass",
    "Drums": "drums",
    "Guitar": "guitar",
    "Piano": "piano",
    "No Other": "no_other",
    "No Bass": "no_bass",
    "No Drums": "no_drums",
    "No Guitar": "no_guitar",
    "No Piano": "no_piano",
}
STEM_TITLE = {value: key for key, value in STEM_ID.items()}
STEM_PAIR = {
    "vocals": "instrumental",
    "instrumental": "vocals",
    "drums": "no_drums",
    "bass": "no_bass",
    "other": "no_other",
    "guitar": "no_guitar",
    "piano": "no_piano",
    "no_drums": "drums",
    "no_bass": "bass",
    "no_other": "other",
    "no_guitar": "guitar",
    "no_piano": "piano",
}


def stem_title(target: str) -> str:
    return STEM_TITLE.get(target, target)


def _stem_id(name: str) -> str:
    return STEM_ID.get(name, name)


def training_stems(path: Path) -> tuple[str | None, list[str]]:
    return training_stems_text(path.read_text(encoding="utf-8"))


def training_stems_text(text: str) -> tuple[str | None, list[str]]:
    """Read the training block the way UVR does: target_instrument, else instruments."""
    target: str | None = None
    instruments: list[str] = []
    in_training = False
    in_instruments = False
    for line in text.splitlines():
        if line.startswith("training:"):
            in_training = True
            in_instruments = False
            continue
        if in_training and line and not line.startswith((" ", "\t")):
            break
        if not in_training:
            continue
        stripped = line.strip()
        if stripped.startswith("target_instrument:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            target = None if value in ("", "null", "~") else value
            in_instruments = False
            continue
        if stripped.startswith("instruments:"):
            in_instruments = True
            continue
        if in_instruments and stripped.startswith("- "):
            instruments.append(stripped[2:].strip().strip("'\""))
            continue
        if in_instruments:
            in_instruments = False
    return target, instruments


def output_menu(
    arch: str,
    model_name: str,
    stems: list[str] | None = None,
    target_instrument: str | None = None,
) -> list[str]:
    """Stem menu for one model. Demucs follows the name; MDX follows its config."""
    arch = (arch or "").lower()
    name = model_name or ""
    folded = name.lower()
    if arch == "demucs":
        if "UVR_Model" in name or "uvr model" in folded or "2stem" in folded:
            return ["vocals", "instrumental", "all"]
        if "htdemucs_6s" in folded or "6s" in folded:
            return ["all", "vocals", "other", "bass", "drums", "guitar", "piano"]
        return ["all", "vocals", "other", "bass", "drums"]
    if target_instrument:
        return [_stem_id(target_instrument)]
    if stems:
        names = [_stem_id(item) for item in stems if item]
        if len(names) >= 3:
            return ["all", *names]
        if len(names) == 2:
            return [*names, "all"]
        if len(names) == 1:
            return names
    if any(token in folded for token in ("4-stem", "4_stem", "4 stem", "4stem")):
        return ["all", "vocals", "drums", "bass", "other"]
    primary = infer_primary(name)
    secondary = STEM_PAIR.get(primary, "instrumental")
    return [primary, secondary, "all"]


def _known_output(arch: str, model_name: str, output_target: str) -> bool:
    if output_target in output_menu(arch, model_name):
        return True
    if arch != "mdx" or not output_target or len(output_target) > 40:
        return False
    return all(ch.isalnum() or ch in " _+-." for ch in output_target)


def infer_primary(model_name: str, explicit: str | None = None) -> str:
    if explicit in ("instrumental", "vocals", "drums", "bass", "other"):
        return explicit
    folded = model_name.lower()
    if any(token in folded for token in ("inst", "karaoke", "instrumental")):
        return "instrumental"
    if "drum" in folded:
        return "drums"
    if "bass" in folded:
        return "bass"
    return "vocals"


def _wav_type(value: Any) -> str:
    wav = str(value or "PCM_24")
    if wav not in WAV_TYPES:
        raise SpecError("导出格式只支持 WAV 16-bit 或 WAV 24-bit")
    return wav


def _batch(value: Any) -> int:
    try:
        batch = int(value if value is not None else 1)
    except (TypeError, ValueError) as exc:
        raise SpecError("batch size 不是整数") from exc
    if batch < 1 or batch > 8:
        raise SpecError("batch size 需要在 1 到 8 之间")
    return batch


def normalize_params(arch: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    if arch == "mdx":
        try:
            overlap = round(float(raw.get("overlap", 0.25)), 2)
            segment = int(raw.get("segment_size", 256))
        except (TypeError, ValueError) as exc:
            raise SpecError("MDX 参数无法读取") from exc
        if overlap < 0.25 or overlap > 0.99:
            raise SpecError("MDX overlap 需要在 0.25 到 0.99 之间")
        if segment < 32 or segment > 1024:
            raise SpecError("segment size 需要在 32 到 1024 之间")
        params: dict[str, Any] = {
            "segment_size": segment,
            "overlap": overlap,
            "batch_size": _batch(raw.get("batch_size", 1)),
            "wav_type": _wav_type(raw.get("wav_type")),
        }
        if raw.get("overlap_mdxc") is not None:
            try:
                mdxc = int(raw["overlap_mdxc"])
            except (TypeError, ValueError) as exc:
                raise SpecError("MDX-C overlap 不是整数") from exc
            if mdxc < 2 or mdxc > 50:
                raise SpecError("MDX-C overlap 需要在 2 到 50 之间")
            params["overlap_mdxc"] = mdxc
        return params
    if arch == "vr":
        try:
            window = int(raw.get("window_size", 512))
            aggression = int(raw.get("aggression", 5))
        except (TypeError, ValueError) as exc:
            raise SpecError("VR 参数无法读取") from exc
        if window not in (320, 512, 1024):
            raise SpecError("VR window size 只支持 320、512 或 1024")
        if aggression < 0 or aggression > 50:
            raise SpecError("VR aggression 需要在 0 到 50 之间")
        return {
            "window_size": window,
            "aggression": aggression,
            "tta": bool(raw.get("tta", False)),
            "batch_size": _batch(raw.get("batch_size", 1)),
            "wav_type": _wav_type(raw.get("wav_type")),
        }
    if arch == "demucs":
        try:
            shifts = int(raw.get("shifts", 2))
            overlap = round(float(raw.get("overlap", 0.25)), 2)
        except (TypeError, ValueError) as exc:
            raise SpecError("Demucs 参数无法读取") from exc
        if shifts < 0 or shifts > 10:
            raise SpecError("Demucs shifts 需要在 0 到 10 之间")
        if overlap < 0.0 or overlap > 0.95:
            raise SpecError("Demucs overlap 需要在 0 到 0.95 之间")
        return {
            "shifts": shifts,
            "overlap": overlap,
            "batch_size": _batch(raw.get("batch_size", 1)),
            "wav_type": _wav_type(raw.get("wav_type")),
        }
    raise SpecError(f"不支持的架构 {arch}")


def summarize(spec: dict[str, Any]) -> str:
    name = spec["model_name"]
    params = spec["params"]
    if spec["arch"] == "mdx":
        return f"{name} · overlap {params['overlap']}"
    if spec["arch"] == "vr":
        return f"{name} · aggression {params['aggression']}"
    return f"{name} · shifts {params['shifts']}"


def make_spec(
    arch: str,
    model_name: str,
    output_target: str,
    params: dict[str, Any] | None = None,
    primary_stem: str | None = None,
) -> dict[str, Any]:
    arch = (arch or "").lower()
    if arch not in ARCHES:
        raise SpecError("架构只支持 mdx、vr 或 demucs")
    model_name = (model_name or "").strip()
    if not model_name or len(model_name) > 180:
        raise SpecError("缺少模型名称")
    if not _known_output(arch, model_name, output_target):
        allowed = "、".join(output_menu(arch, model_name))
        raise SpecError(f"{model_name} 可输出的音轨是 {allowed}")
    spec = {
        "arch": arch,
        "model_name": model_name,
        "output_target": output_target,
        "primary_stem": infer_primary(model_name, primary_stem),
        "params": normalize_params(arch, params),
    }
    spec["summary"] = summarize(spec)
    return spec


def default_draft(duration: float | None) -> dict[str, Any]:
    preset = default_preset()
    end = 30.0 if not duration or duration <= 0 else min(30.0, float(duration))
    spec = make_spec(
        preset["arch"],
        preset["model_name"],
        preset["output_target"],
        preset["params"],
        preset.get("primary_stem"),
    )
    return {
        **spec,
        "start_sec": 0.0,
        "end_sec": round(end, 3),
    }


def draft_to_spec(draft: dict[str, Any]) -> dict[str, Any]:
    return make_spec(
        draft.get("arch", "mdx"),
        draft.get("model_name", ""),
        draft.get("output_target", "instrumental"),
        draft.get("params") or {},
        draft.get("primary_stem"),
    )


def preview_range(duration: float | None, draft: dict[str, Any]) -> tuple[float, float]:
    try:
        start = float(draft.get("start_sec") or 0)
    except (TypeError, ValueError) as exc:
        raise SpecError("试听起点无法读取") from exc
    end_raw = draft.get("end_sec")
    try:
        end = None if end_raw is None or end_raw == "" else float(end_raw)
    except (TypeError, ValueError) as exc:
        raise SpecError("试听终点无法读取") from exc
    if duration and duration > 0:
        if end is None:
            end = min(30.0, duration)
        start = max(0.0, start)
        end = min(end, float(duration))
    else:
        if end is None:
            end = start + 30.0
    if end - start < 0.1:
        raise SpecError("试听区间太短")
    if end - start > 120:
        raise SpecError("试听区间最长 120 秒")
    return round(start, 3), round(end, 3)


def quality_signature(spec: dict[str, Any]) -> str:
    params = {key: value for key, value in spec["params"].items() if key != "batch_size"}
    body = {
        "arch": spec["arch"],
        "model": spec["model_name"],
        "target": spec["output_target"],
        "params": params,
    }
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def spec_key(task_id: str, kind: str, spec: dict[str, Any], start: float | None, end: float | None) -> str:
    body = {
        "task": task_id,
        "kind": kind,
        "arch": spec["arch"],
        "model": spec["model_name"],
        "target": spec["output_target"],
        "params": spec["params"],
        "start": None if start is None else round(float(start), 3),
        "end": None if end is None else round(float(end), 3),
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
