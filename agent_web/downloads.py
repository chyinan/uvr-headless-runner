"""Single model download, separate from the inference slot."""

from __future__ import annotations

import sys
import threading
from pathlib import Path


class DownloadManager:
    def __init__(self, repo_root: Path, database, on_finished):
        self.repo_root = Path(repo_root)
        self.db = database
        self.on_finished = on_finished
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = False

    def enqueue(self, arch: str, model_name: str, request_key: str | None = None) -> dict:
        from agent_web.util import new_id, now_iso

        with self.db.transaction() as tx:
            if request_key:
                existing = tx.one(
                    "SELECT * FROM download_jobs WHERE request_key=? ORDER BY created_at ASC LIMIT 1",
                    (request_key,),
                )
                if existing:
                    return dict(existing)
            active = tx.one(
                """
                SELECT * FROM download_jobs
                WHERE arch=? AND model_name=? AND status IN ('queued', 'running')
                ORDER BY created_at ASC LIMIT 1
                """,
                (arch, model_name),
            )
            if active:
                return dict(active)
            stamp = now_iso()
            job_id = new_id()
            tx.execute(
                """
                INSERT INTO download_jobs
                (id, model_name, arch, status, progress, stage, error, request_key, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', NULL, 'queued', '', ?, ?, ?)
                """,
                (job_id, model_name, arch, request_key, stamp, stamp),
            )
            row = tx.one("SELECT * FROM download_jobs WHERE id=?", (job_id,))
        self._ensure_thread()
        return dict(row)

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            self._wake.set()
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="uvr-download", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop:
            with self.db.transaction() as tx:
                row = tx.one(
                    """
                    SELECT * FROM download_jobs
                    WHERE status='queued'
                    ORDER BY created_at ASC LIMIT 1
                    """
                )
                if row:
                    tx.execute(
                        "UPDATE download_jobs SET status='running', stage='download', updated_at=? WHERE id=?",
                        (_stamp(), row["id"]),
                    )
            if not row:
                self._wake.wait(0.4)
                self._wake.clear()
                if self._stop:
                    return
                with self.db.transaction() as tx:
                    more = tx.one("SELECT id FROM download_jobs WHERE status='queued' LIMIT 1")
                if not more:
                    return
                continue
            ok, message = self._download(dict(row))
            with self.db.transaction() as tx:
                if ok:
                    tx.execute(
                        """
                        UPDATE download_jobs
                        SET status='succeeded', progress=100, stage='complete', error='', updated_at=?
                        WHERE id=?
                        """,
                        (_stamp(), row["id"]),
                    )
                else:
                    tx.execute(
                        """
                        UPDATE download_jobs
                        SET status='failed', stage='failed', error=?, updated_at=?
                        WHERE id=?
                        """,
                        (message[:800], _stamp(), row["id"]),
                    )
            self.on_finished(row["arch"], row["model_name"], ok, message)

    def _download(self, job: dict) -> tuple[bool, str]:
        root = str(self.repo_root)
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from model_downloader import ModelDownloader
        except Exception as exc:
            return False, f"无法加载下载器：{exc}"

        def callback(current, total, _filename):
            progress = None
            stage = "download"
            if total and total > 0:
                progress = max(0.0, min(100.0, (current / total) * 100))
            else:
                stage = "size_unknown"
            with self.db.transaction() as tx:
                tx.execute(
                    "UPDATE download_jobs SET progress=?, stage=?, updated_at=? WHERE id=? AND status='running'",
                    (progress, stage, _stamp(), job["id"]),
                )

        try:
            downloader = ModelDownloader(base_path=root, verbose=False)
            ok, message = downloader.download_model(job["model_name"], job["arch"], progress_callback=callback)
            return bool(ok), str(message)
        except Exception as exc:
            return False, str(exc)


def _stamp() -> str:
    from agent_web.util import now_iso

    return now_iso()
