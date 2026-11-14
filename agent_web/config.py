"""Settings for the control service. Secrets stay in the local config file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


@dataclass
class Settings:
    host: str
    port: int
    repo_root: Path
    data_dir: Path
    inference_python: list[str]
    device: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key.strip() and self.llm_model.strip() and self.llm_base_url.strip())


def load_settings() -> Settings:
    example = PACKAGE_DIR / "config.example.json"
    local = PACKAGE_DIR / "config.json"
    payload: dict = {}
    if local.is_file():
        with local.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    elif example.is_file():
        with example.open(encoding="utf-8") as handle:
            payload = json.load(handle)

    data_dir = payload.get("data_dir") or os.environ.get("UVR_AGENT_DATA_DIR") or str(PACKAGE_DIR / "data")
    python = payload.get("inference_python") or ["python"]
    env_python = os.environ.get("UVR_AGENT_INFERENCE_PYTHON")
    if env_python:
        python = [env_python]
    if isinstance(python, str):
        python = [python]
    llm = payload.get("llm") or {}
    api_key = os.environ.get("UVR_AGENT_LLM_API_KEY") or llm.get("api_key") or ""
    device = payload.get("device") or "auto"
    if device not in ("auto", "gpu", "cpu"):
        device = "auto"
    return Settings(
        host=str(payload.get("host") or "127.0.0.1"),
        port=int(payload.get("port") or 8787),
        repo_root=REPO_ROOT,
        data_dir=Path(data_dir),
        inference_python=[str(part) for part in python if str(part).strip()],
        device=device,
        llm_base_url=str(llm.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
        llm_api_key=str(api_key),
        llm_model=str(llm.get("model") or "gpt-4o-mini"),
    )
