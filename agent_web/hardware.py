"""One cached snapshot of the machine that runs this service."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class HardwareMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = {
            "sampled_at": None,
            "cpu_percent": None,
            "memory_used": None,
            "memory_total": None,
            "gpu": {"available": False, "name": None, "utilization": None, "memory_used": None, "memory_total": None},
            "error": "",
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._snapshot = _sample()
        self._thread = threading.Thread(target=self._loop, name="uvr-hardware", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return json_copy(self._snapshot)

    def has_nvidia(self) -> bool:
        snap = self.snapshot()
        return bool(snap.get("gpu", {}).get("available"))

    def _loop(self) -> None:
        while not self._stop.wait(3):
            snap = _sample()
            with self._lock:
                self._snapshot = snap


def json_copy(value):
    return {
        "sampled_at": value.get("sampled_at"),
        "cpu_percent": value.get("cpu_percent"),
        "memory_used": value.get("memory_used"),
        "memory_total": value.get("memory_total"),
        "gpu": dict(value.get("gpu") or {}),
        "error": value.get("error") or "",
    }


def _sample() -> dict:
    snap = {
        "sampled_at": _now(),
        "cpu_percent": None,
        "memory_used": None,
        "memory_total": None,
        "gpu": {"available": False, "name": None, "utilization": None, "memory_used": None, "memory_total": None},
        "error": "",
    }
    errors = []
    try:
        import psutil

        snap["cpu_percent"] = round(float(psutil.cpu_percent(interval=None)), 1)
        memory = psutil.virtual_memory()
        snap["memory_used"] = int(memory.used)
        snap["memory_total"] = int(memory.total)
    except Exception as exc:
        errors.append(f"cpu: {exc}")
    try:
        snap["gpu"] = _nvidia()
    except Exception as exc:
        errors.append(f"gpu: {exc}")
        snap["gpu"] = {"available": False, "name": None, "utilization": None, "memory_used": None, "memory_total": None}
    snap["error"] = "; ".join(errors)
    return snap


def _nvidia() -> dict:
    import pynvml

    pynvml.nvmlInit()
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return {
            "available": True,
            "name": str(name),
            "utilization": int(util.gpu),
            "memory_used": int(memory.used),
            "memory_total": int(memory.total),
        }
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def prime_cpu() -> None:
    try:
        import psutil

        psutil.cpu_percent(interval=None)
    except Exception:
        return
