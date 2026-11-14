"""Local FastAPI control service. Bind it to loopback."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_web.agent import Agent
from agent_web.catalog import Catalog
from agent_web.config import load_settings
from agent_web.db import Database
from agent_web.downloads import DownloadManager
from agent_web.executor import ProcessExecutor
from agent_web.hardware import HardwareMonitor, prime_cpu
from agent_web.service import ServiceError, TaskService
from agent_web.spec import TARGETS, WAV_TYPES, load_presets

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif", ".m4a"}
DIST = Path(__file__).resolve().parents[1] / "webui" / "dist"
log = logging.getLogger("uvr.agent")


class DraftBody(BaseModel):
    draft: dict = Field(default_factory=dict)


class PreviewBody(BaseModel):
    draft: dict | None = None
    request_key: str | None = None
    reason: str = ""


class SelectBody(BaseModel):
    variant_id: str


class RunBody(BaseModel):
    variant_id: str | None = None
    target_task_ids: list[str] | None = None
    request_key: str | None = None
    reason: str = ""


class ChatBody(BaseModel):
    text: str
    target_task_ids: list[str] | None = None


class DownloadBody(BaseModel):
    arch: str
    model_name: str
    request_key: str | None = None


def create_app(settings=None, service: TaskService | None = None, agent: Agent | None = None, catalog: Catalog | None = None, hardware: HardwareMonitor | None = None) -> FastAPI:
    settings = settings or load_settings()
    if service is None or agent is None or catalog is None or hardware is None:
        service, agent, catalog, hardware = build_runtime(settings)
    app = FastAPI(title="UVR Agent Workbench", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.service = service
    app.state.agent = agent
    app.state.catalog = catalog
    app.state.hardware = hardware
    app.state.torch_version = None

    @app.exception_handler(ServiceError)
    def _service_error(_request, exc: ServiceError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.on_event("startup")
    def _startup():
        prime_cpu()
        hardware.start()
        service.recover_after_restart()
        service.start()
        threading.Thread(target=_warm, args=(catalog, app), daemon=True).start()

    @app.on_event("shutdown")
    def _shutdown():
        service.stop()
        hardware.stop()

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "llm_configured": settings.llm_configured,
            "device": settings.device,
            "inference_python": settings.inference_python,
            "inference_blocked": service.executor.leftover_blocking(),
            "torch": app.state.torch_version,
            "data_dir": str(settings.data_dir),
        }

    @app.get("/api/hardware")
    def hardware_snapshot():
        return hardware.snapshot()

    @app.get("/api/meta")
    def meta():
        return {"presets": load_presets(), "targets": TARGETS, "wav_types": list(WAV_TYPES)}

    @app.get("/api/tasks")
    def tasks(scope: str = "all"):
        if scope not in ("all", "active", "done"):
            raise HTTPException(400, "未知的筛选")
        return {"tasks": service.list_tasks(scope)}

    @app.post("/api/tasks")
    def upload(file: UploadFile = File(...)):
        name = file.filename or "audio.wav"
        suffix = Path(name).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            raise HTTPException(400, "只接受 wav、flac、mp3、ogg、aiff 或 m4a")
        from agent_web.util import new_id

        folder = settings.data_dir / "incoming"
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f"{new_id()}{suffix}"
        with temporary.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        try:
            return service.create_task(temporary, name)
        finally:
            temporary.unlink(missing_ok=True)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        return service.get_task(task_id)

    @app.patch("/api/tasks/{task_id}/draft")
    def draft(task_id: str, body: DraftBody):
        return service.update_draft(task_id, body.draft)

    @app.post("/api/tasks/{task_id}/preview")
    def preview(task_id: str, body: PreviewBody):
        return service.create_preview(task_id, body.draft, body.request_key, "manual", body.reason or "手动提交试听")

    @app.post("/api/tasks/{task_id}/select")
    def select(task_id: str, body: SelectBody):
        return service.select_variant(task_id, body.variant_id)

    @app.post("/api/tasks/{task_id}/run")
    def run(task_id: str, body: RunBody):
        return {
            "jobs": service.run_full(
                task_id,
                body.variant_id,
                body.target_task_ids,
                body.request_key,
                "manual",
                body.target_task_ids,
                body.reason or "手动处理整首",
            )
        }

    @app.get("/api/tasks/{task_id}/messages")
    def messages(task_id: str):
        return {"messages": service.list_messages(task_id)}

    @app.post("/api/tasks/{task_id}/messages")
    def speak(task_id: str, body: ChatBody):
        service.add_message(task_id, "user", body.text)
        agent.run(task_id, body.target_task_ids or [task_id])
        return {"task": service.get_task(task_id), "messages": service.list_messages(task_id)}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return service.cancel_job(job_id)

    @app.post("/api/jobs/{job_id}/retry")
    def retry(job_id: str):
        return service.retry_job(job_id)

    @app.post("/api/jobs/{job_id}/continue")
    def continue_job(job_id: str):
        return service.continue_job(job_id)

    @app.get("/api/tasks/{task_id}/source")
    def source(task_id: str):
        path = service.task_audio(task_id)
        return FileResponse(path, filename=path.name)

    @app.get("/api/artifacts/{artifact_id}/audio")
    def artifact(artifact_id: str):
        path, label = service.artifact_audio(artifact_id)
        return FileResponse(path, filename=f"{label}{path.suffix}")

    @app.get("/api/models")
    def models(arch: str | None = None, q: str = "", installed: str | None = None):
        return {"models": catalog.list_models(arch=arch, query=q, installed=installed), "warning": catalog.last_error()}

    @app.post("/api/models/download")
    def download_model(body: DownloadBody):
        if body.arch not in ("mdx", "vr", "demucs"):
            raise HTTPException(400, "架构只支持 mdx、vr 或 demucs")
        if not catalog.is_known(body.arch, body.model_name):
            raise HTTPException(400, "模型不在官方目录里")
        job = service.downloads.enqueue(body.arch, body.model_name, body.request_key)
        return {
            "id": job["id"],
            "model_name": job["model_name"],
            "arch": job["arch"],
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "error": job["error"],
        }

    @app.get("/api/downloads")
    def downloads():
        return {"downloads": service.list_downloads()}

    if DIST.is_dir():
        assets = DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index():
            return FileResponse(DIST / "index.html")

        @app.get("/{path:path}")
        def frontend(path: str):
            target = (DIST / path).resolve()
            if target.is_file() and DIST.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(DIST / "index.html")

    return app


def build_runtime(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    database = Database(settings.data_dir / "agent.sqlite3")
    catalog = Catalog(settings.repo_root)
    executor = ProcessExecutor(settings.data_dir)
    hardware = HardwareMonitor()
    holder: dict = {}

    def finished(arch, name, ok, message):
        holder["service"].on_download_finished(arch, name, ok, message)

    downloads = DownloadManager(settings.repo_root, database, finished)
    service = TaskService(settings, database, catalog, executor, downloads, hardware)
    holder["service"] = service
    agent = Agent(service, settings, catalog, hardware)
    return service, agent, catalog, hardware


def _warm(catalog: Catalog, app: FastAPI) -> None:
    try:
        catalog.refresh()
    except Exception:
        log.exception("model registry warmup failed")
    app.state.torch_version = _torch_version(app.state.settings.inference_python)


def _torch_version(python: list[str]) -> str | None:
    try:
        result = subprocess.run(
            [*python, "-c", "import torch; print(torch.__version__)"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()[:80] or None


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
