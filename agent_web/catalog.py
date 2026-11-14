"""Official model registry through the existing downloader. No torch import."""

from __future__ import annotations

import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_web.spec import load_presets, output_menu, training_stems, training_stems_text

MDX_CONFIG_URL = "https://raw.githubusercontent.com/TRvlvr/application_data/main/mdx_model_data/mdx_c_configs/"
_YAML_CACHE: dict[str, str] = {}


class Catalog:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._models: list[dict] = []
        self._error = ""

    def refresh(self, force: bool = False) -> list[dict]:
        with self._lock:
            fresh = self._models and (time.time() - self._loaded_at) < 30 and not force
            if fresh:
                return list(self._models)
        models, error = self._load()
        with self._lock:
            self._models = models
            self._error = error
            self._loaded_at = time.time()
            return list(self._models)

    def invalidate(self) -> None:
        with self._lock:
            self._loaded_at = 0.0

    def last_error(self) -> str:
        with self._lock:
            return self._error

    def is_known(self, arch: str, name: str) -> bool:
        if _preset_match(arch, name):
            return True
        try:
            models = self.refresh()
        except Exception:
            return False
        return any(item["arch"] == arch and item["name"] == name for item in models)

    def is_installed(self, arch: str, name: str) -> bool:
        try:
            models = self.refresh()
        except Exception:
            return False
        return any(item["arch"] == arch and item["name"] == name and item["installed"] for item in models)

    def list_models(self, arch: str | None = None, query: str = "", installed: str | None = None) -> list[dict]:
        models = self.refresh()
        needle = query.strip().lower()
        result = []
        for item in models:
            if arch and item["arch"] != arch:
                continue
            if needle and needle not in item["name"].lower() and needle not in item["display_name"].lower():
                continue
            if installed == "yes" and not item["installed"]:
                continue
            if installed == "no" and item["installed"]:
                continue
            result.append(item)
        return result

    def _load(self) -> tuple[list[dict], str]:
        root = str(self.repo_root)
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from model_downloader import ModelDownloader

            downloader = ModelDownloader(base_path=root, verbose=False)
            downloader.sync_registry()
            items: list[dict] = []
            listed = [(arch, model) for arch in ("mdx", "vr", "demucs") for model in downloader.list_models(arch, show_installed=True)]
            _warm_configs(self.repo_root, listed)
            for arch, model in listed:
                files = model.get("files") or []
                target, stems = _config_stems(self.repo_root, files) if arch == "mdx" else (None, None)
                items.append(
                        {
                            "name": model["name"],
                            "display_name": model.get("display_name") or model["name"],
                            "arch": arch,
                            "installed": bool(model.get("installed")),
                            "executable": True,
                            "files": files,
                            "outputs": output_menu(arch, model["name"], stems, target),
                        }
                    )
            return items, ""
        except Exception as exc:
            fallback = [
                {
                    "name": preset["model_name"],
                    "display_name": preset["model_name"],
                    "arch": preset["arch"],
                    "installed": False,
                    "executable": True,
                    "files": [],
                    "outputs": output_menu(preset["arch"], preset["model_name"]),
                }
                for preset in load_presets()
            ]
            return fallback, str(exc)


def _config_roots(repo: Path) -> tuple[Path, Path]:
    return (
        repo / "models" / "MDX_Net_Models" / "model_data" / "mdx_c_configs",
        repo / "models" / "MDX_Net_Models",
    )


def _local_config(repo: Path, filename: str) -> Path | None:
    for folder in _config_roots(repo):
        path = folder / filename
        if path.is_file():
            return path
    return None


def _warm_configs(repo: Path, listed: list[tuple[str, dict]]) -> None:
    missing = []
    for arch, model in listed:
        if arch != "mdx":
            continue
        for filename in model.get("files") or []:
            name = str(filename)
            if not name.endswith((".yaml", ".yml")) or name in _YAML_CACHE or _local_config(repo, name):
                continue
            missing.append(name)
    if not missing:
        return

    def fetch(name: str) -> tuple[str, str]:
        try:
            with urllib.request.urlopen(MDX_CONFIG_URL + name, timeout=12) as response:
                return name, response.read().decode("utf-8")
        except Exception:
            return name, ""

    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, text in pool.map(fetch, missing):
            _YAML_CACHE[name] = text


def _config_stems(repo: Path, files: list) -> tuple[str | None, list[str] | None]:
    for filename in files:
        name = str(filename)
        if not name.endswith((".yaml", ".yml")):
            continue
        local = _local_config(repo, name)
        if local:
            return training_stems(local)
        text = _YAML_CACHE.get(name) or ""
        if text:
            return training_stems_text(text)
    return None, None


def _preset_match(arch: str, name: str) -> bool:
    return any(preset["arch"] == arch and preset["model_name"] == name for preset in load_presets())
