"""Read and cut local audio without importing the inference stack."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path


class AudioError(RuntimeError):
    pass


def probe(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"找不到音频文件 {path.name}")
    if path.suffix.lower() == ".wav":
        try:
            return _probe_wave(path)
        except wave.Error:
            pass
    probed = _probe_soundfile(path)
    if probed:
        return probed
    probed = _probe_ffprobe(path)
    if probed:
        return probed
    raise AudioError("无法读取音频。wav 可直接使用；其他格式需要本机的 soundfile 或 ffmpeg")


def trim_to_wav(src: Path, dst: Path, start: float, end: float) -> dict:
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".wav":
        try:
            _trim_wave(src, dst, start, end)
            meta = probe(dst)
            if meta["duration_sec"] <= 0:
                raise AudioError("切出的试听片段是空的")
            return meta
        except wave.Error:
            pass
    if _trim_soundfile(src, dst, start, end):
        meta = probe(dst)
        if meta["duration_sec"] <= 0:
            raise AudioError("切出的试听片段是空的")
        return meta
    if shutil.which("ffmpeg"):
        _trim_ffmpeg(src, dst, start, end)
        meta = probe(dst)
        if meta["duration_sec"] <= 0:
            raise AudioError("切出的试听片段是空的")
        return meta
    raise AudioError("无法裁剪这段音频。请上传 wav，或安装 ffmpeg")


def _probe_wave(path: Path) -> dict:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.getnframes()
        channels = handle.getnchannels()
    if rate <= 0 or frames <= 0:
        raise AudioError("wav 文件没有可播放的采样")
    return {
        "duration_sec": frames / float(rate),
        "sample_rate": rate,
        "channels": channels,
        "format": "wav",
    }


def _trim_wave(src: Path, dst: Path, start: float, end: float) -> None:
    with wave.open(str(src), "rb") as handle:
        rate = handle.getframerate()
        first = max(0, int(start * rate))
        last = max(first + 1, int(end * rate))
        last = min(last, handle.getnframes())
        handle.setpos(first)
        frames = handle.readframes(last - first)
        params = handle.getparams()
    with wave.open(str(dst), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(frames)


def _probe_soundfile(path: Path) -> dict | None:
    try:
        import soundfile as sf
    except ImportError:
        return None
    try:
        info = sf.info(str(path))
    except Exception:
        return None
    if not info.samplerate or info.frames <= 0:
        return None
    return {
        "duration_sec": info.frames / float(info.samplerate),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "format": path.suffix.lower().lstrip(".") or "audio",
    }


def _trim_soundfile(src: Path, dst: Path, start: float, end: float) -> bool:
    try:
        import soundfile as sf
    except ImportError:
        return False
    try:
        info = sf.info(str(src))
        first = max(0, int(start * info.samplerate))
        last = max(first + 1, int(end * info.samplerate))
        data, rate = sf.read(str(src), start=first, stop=last, always_2d=True)
        sf.write(str(dst), data, rate, subtype="PCM_16")
    except Exception:
        return False
    return True


def _probe_ffprobe(path: Path) -> dict | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    streams = payload.get("streams") or []
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not audio:
        return None
    try:
        rate = int(float(audio.get("sample_rate") or 0))
        channels = int(audio.get("channels") or 0)
        duration = float(payload.get("format", {}).get("duration") or audio.get("duration") or 0)
    except (TypeError, ValueError):
        return None
    if rate <= 0 or channels <= 0 or duration <= 0:
        return None
    return {
        "duration_sec": duration,
        "sample_rate": rate,
        "channels": channels,
        "format": path.suffix.lower().lstrip(".") or "audio",
    }


def _trim_ffmpeg(src: Path, dst: Path, start: float, end: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioError("找不到 ffmpeg")
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                str(start),
                "-to",
                str(end),
                "-i",
                str(src),
                "-vn",
                "-acodec",
                "pcm_s16le",
                str(dst),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioError("ffmpeg 裁剪失败") from exc
    if result.returncode != 0 or not dst.is_file():
        tail = (result.stderr or b"")[-400:].decode("utf-8", "replace")
        raise AudioError(f"ffmpeg 裁剪失败：{tail}")
