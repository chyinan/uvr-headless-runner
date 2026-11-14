"""One inference subprocess. A leftover process from the last run blocks a new one."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from agent_web.audio_util import AudioError, probe, trim_to_wav

PERCENT = __import__("re").compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
STAGE_KEYS = (
    ("download", ("download", "下载模型")),
    ("load", ("loading model", "load model", "加载模型")),
    ("inference", ("inference", "processing audio", "separat", "推理")),
    ("save", ("saving", "保存")),
)


class ProcessExecutor:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.pidfile = self.data_dir / "worker.pid"
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._job_id: str | None = None
        self._starting = False
        self._leftover_checked = 0.0
        self._leftover = False

    def busy(self) -> bool:
        with self._lock:
            if self._starting:
                return True
            return self._proc is not None and self._proc.poll() is None

    def leftover_blocking(self) -> bool:
        now = __import__("time").time()
        if now - self._leftover_checked < 2:
            return self._leftover
        self._leftover_checked = now
        self._leftover = _pidfile_is_our_worker(self.pidfile)
        return self._leftover

    def start(self, job: dict, task: dict, argv: list[str], cwd: Path, on_progress, on_exit, stop_requested) -> None:
        with self._lock:
            if self._starting or (self._proc is not None and self._proc.poll() is None):
                raise RuntimeError("推理进程已经在运行")
            self._starting = True
            self._job_id = job["id"]
        thread = threading.Thread(
            target=self._run,
            args=(job, task, argv, cwd, on_progress, on_exit, stop_requested),
            name=f"uvr-job-{job['id']}",
            daemon=True,
        )
        thread.start()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            proc = self._proc if self._job_id == job_id else None
        if proc and proc.poll() is None:
            _kill_tree(proc.pid)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()

    def shutdown(self) -> None:
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            _kill_tree(proc.pid)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _run(self, job, task, argv, cwd, on_progress, on_exit, stop_requested) -> None:
        code = 1
        tail = ""
        outputs: list[Path] = []
        try:
            if stop_requested():
                return
            input_path = self._prepare_input(job, task, on_progress)
            if str(input_path) not in argv:
                raise RuntimeError("分离命令没有使用准备好的音频")
            if stop_requested():
                return
            on_progress(job["id"], "running", None)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            _prepend_torch_libs(env, argv)
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            with self._lock:
                self._proc = proc
                self._job_id = job["id"]
            _write_pid(self.pidfile, proc.pid)
            tail, code = _read_process(proc, job["id"], on_progress)
            outputs = _outputs(Path(job["output_dir"]))
        except Exception as exc:
            tail = str(exc)
            code = 1
        finally:
            with self._lock:
                if self._job_id == job["id"]:
                    self._proc = None
                    self._job_id = None
                self._starting = False
            _clear_pid(self.pidfile)
            on_exit(job["id"], code, outputs, tail[-4000:])

    def _prepare_input(self, job, task, on_progress) -> Path:
        output = Path(job["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        source = Path(task["stored_path"])
        if job["kind"] != "preview":
            return source
        on_progress(job["id"], "preparing", None)
        clip = output / "source_clip.wav"
        try:
            trim_to_wav(source, clip, float(job["start_sec"]), float(job["end_sec"]))
            probe(clip)
        except AudioError:
            raise
        return clip


def _prepend_torch_libs(env: dict, argv: list[str]) -> None:
    """ONNX Runtime looks for CUDA DLLs on PATH. The torch wheel already ships them."""
    if not argv:
        return
    root = Path(argv[0]).resolve().parent.parent
    folders = [root / "Lib" / "site-packages" / "torch" / "lib"]
    folders.extend(root.glob("lib/python*/site-packages/torch/lib"))
    for folder in folders:
        if not folder.is_dir():
            continue
        folder_text = str(folder)
        for key in ("PATH", "LD_LIBRARY_PATH"):
            current = env.get(key, "")
            parts = [part for part in current.split(os.pathsep) if part]
            if any(part.lower() == folder_text.lower() for part in parts):
                continue
            env[key] = folder_text + (os.pathsep + current if current else "")
        return


def _outputs(directory: Path) -> list[Path]:
    skip = {"source_clip.wav", "input_clip.wav"}
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.wav") if path.name not in skip)


def _read_process(proc: subprocess.Popen, job_id: str, on_progress) -> tuple[str, int]:
    chunks: list[str] = []
    assert proc.stdout is not None
    while True:
        raw = proc.stdout.read(512)
        if not raw:
            break
        text = raw.decode("utf-8", "replace")
        chunks.append(text)
        stage, progress = _parse_progress(text)
        if stage or progress is not None:
            on_progress(job_id, stage, progress)
    code = proc.wait()
    tail = "".join(chunks)
    if len(tail) > 8000:
        tail = tail[-8000:]
    return tail, int(code if code is not None else 1)


def _parse_progress(text: str) -> tuple[str | None, float | None]:
    folded = text.lower()
    stage = None
    for name, keys in STAGE_KEYS:
        if any(key in folded for key in keys):
            stage = name
    found = PERCENT.findall(text)
    progress = None
    if found:
        value = float(found[-1])
        if 0 <= value <= 100:
            progress = value
    return stage, progress


def explain_failure(tail: str, code: int) -> str:
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    text = (tail or "").strip() or f"worker exit {code}"
    try:
        from error_handler import classify_error

        info = classify_error(RuntimeError(text[-1200:]))
        message = info.get("message") or "分离失败"
        suggestion = info.get("suggestion") or ""
        if suggestion:
            return f"{message}。{suggestion}"
        return str(message)
    except Exception:
        return text[-500:] or f"分离进程退出，代码 {code}"


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _clear_pid(path: Path) -> None:
    try:
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            path.unlink()
    except OSError:
        return


def _pidfile_is_our_worker(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if not _pid_alive(pid):
        _clear_pid(path)
        return False
    command = _command_line(pid)
    if command is None:
        return True
    folded = command.lower()
    if "cli.py" in folded:
        return True
    _clear_pid(path)
    return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _command_line(pid: int) -> str | None:
    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            text = (result.stdout or "").strip()
            return text or None
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\x00", b" ").decode("utf-8", "replace")
    except Exception:
        return None


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    try:
        os.killpg(pid, 15)
    except OSError:
        try:
            os.kill(pid, 15)
        except OSError:
            return
