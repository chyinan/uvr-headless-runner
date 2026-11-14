"""Build a runner argv. The model never supplies a shell string."""

from __future__ import annotations

from pathlib import Path

from agent_web.spec import SpecError, output_menu, stem_title


def build_argv(
    python: list[str],
    repo: Path,
    spec: dict,
    device: str,
    input_path: Path,
    output_dir: Path,
) -> list[str]:
    if device not in ("gpu", "cpu"):
        raise SpecError("设备只能是 gpu 或 cpu")
    arch = spec["arch"]
    params = spec["params"]
    command = list(python) + [
        str(repo / "cli.py"),
        arch,
        "-m",
        spec["model_name"],
        "-i",
        str(input_path),
        "-o",
        str(output_dir),
        "--name",
        "audio",
        "--gpu" if device == "gpu" else "--cpu",
    ]
    if arch == "mdx":
        command += [
            "--segment-size",
            str(params["segment_size"]),
            "--overlap",
            str(params["overlap"]),
            "--batch-size",
            str(params["batch_size"]),
            "--wav-type",
            params["wav_type"],
        ]
        if "overlap_mdxc" in params:
            command += ["--overlap-mdxc", str(params["overlap_mdxc"])]
        command += _stem_flags(spec)
    elif arch == "vr":
        command += [
            "--window-size",
            str(params["window_size"]),
            "--aggression",
            str(params["aggression"]),
            "--batch-size",
            str(params["batch_size"]),
            "--wav-type",
            params["wav_type"],
        ]
        if params.get("tta"):
            command.append("--tta")
        command += _stem_flags(spec)
    elif arch == "demucs":
        command += [
            "--shifts",
            str(params["shifts"]),
            "--overlap",
            str(params["overlap"]),
            "--wav-type",
            params["wav_type"],
        ]
        target = spec["output_target"]
        if target != "all":
            command += ["--stem", stem_title(target)]
    else:
        raise SpecError(f"不支持的架构 {arch}")
    return command


def _stem_flags(spec: dict) -> list[str]:
    target = spec["output_target"]
    menu = output_menu(spec.get("arch", ""), spec.get("model_name", ""))
    named = [item for item in menu if item != "all"]
    multi = len(named) >= 3 or (target not in menu and target != "all")
    if spec.get("arch") == "mdx" and multi:
        if target == "all":
            return ["--stem", "all"]
        return ["--stem", stem_title(target)]
    if target == "all":
        return []
    if target == spec["primary_stem"]:
        return ["--primary-only"]
    return ["--secondary-only"]
