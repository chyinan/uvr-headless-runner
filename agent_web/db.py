"""SQLite storage for tasks, variants, jobs, messages, and downloads."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    duration_sec REAL,
    sample_rate INTEGER,
    channels INTEGER,
    goal TEXT,
    draft_json TEXT NOT NULL,
    selected_variant_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS variants (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    label TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    variant_id TEXT,
    kind TEXT NOT NULL,
    start_sec REAL,
    end_sec REAL,
    status TEXT NOT NULL,
    stage TEXT,
    progress REAL,
    error TEXT,
    note TEXT,
    output_dir TEXT,
    request_key TEXT,
    spec_key TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    hold INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    role TEXT NOT NULL,
    label TEXT NOT NULL,
    path TEXT NOT NULL,
    duration_sec REAL,
    sample_rate INTEGER,
    channels INTEGER,
    format TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    refs_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download_jobs (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    arch TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL,
    stage TEXT,
    error TEXT,
    request_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_task ON jobs(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, hold, created_at);
CREATE INDEX IF NOT EXISTS idx_variants_task ON variants(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_request ON jobs(request_key) WHERE request_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_dl_request ON download_jobs(request_key) WHERE request_key IS NOT NULL;
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def transaction(self):
        return _Transaction(self)

    def close(self) -> None:
        with self.lock:
            self.conn.close()


class _Transaction:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.db.conn.rollback()
            else:
                self.db.conn.commit()
        finally:
            self.db.lock.release()
        return False

    def execute(self, sql: str, params: tuple = ()):
        return self.db.conn.execute(sql, params)

    def query(self, sql: str, params: tuple = ()):
        return self.db.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()):
        return self.db.conn.execute(sql, params).fetchone()
