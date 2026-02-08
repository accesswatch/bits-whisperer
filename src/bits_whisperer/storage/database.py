"""SQLite database for job metadata and transcript storage."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from bits_whisperer.core.job import (
    Job,
    JobStatus,
    TranscriptionResult,
    TranscriptSegment,
)
from bits_whisperer.utils.constants import DB_PATH

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    source_path   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    provider      TEXT,
    model         TEXT,
    language      TEXT,
    progress      REAL DEFAULT 0.0,
    error_message TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    completed_at  TEXT,
    duration_s    REAL DEFAULT 0.0,
    cost          REAL DEFAULT 0.0,
    output_path   TEXT,
    full_text     TEXT,
    segments_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
"""


class Database:
    """Thin SQLite wrapper for persisting transcription jobs.

    Thread-safety: each call acquires its own connection via the
    context manager so the database can be used from worker threads.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Connection helpers                                                   #
    # ------------------------------------------------------------------ #

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLES)
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (_SCHEMA_VERSION,),
                )

    # ------------------------------------------------------------------ #
    # Job CRUD                                                             #
    # ------------------------------------------------------------------ #

    def save_job(self, job: Job) -> None:
        """Insert or replace a job record."""
        segments_json: str | None = None
        if job.result and job.result.segments:
            segments_json = json.dumps(
                [
                    {
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                        "confidence": s.confidence,
                        "speaker": s.speaker,
                    }
                    for s in job.result.segments
                ],
                ensure_ascii=False,
            )

        full_text = job.result.full_text if job.result else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                    (id, source_path, status, provider, model, language,
                     progress, error_message, created_at, started_at,
                     completed_at, duration_s, cost, output_path,
                     full_text, segments_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job.id,
                    str(job.file_path),
                    job.status.value,
                    job.provider,
                    job.model,
                    job.language,
                    job.progress_percent,
                    job.error_message,
                    job.created_at,
                    job.started_at,
                    job.completed_at,
                    job.result.duration_seconds if job.result else 0.0,
                    job.cost_actual,
                    job.transcript_path or None,
                    full_text,
                    segments_json,
                ),
            )

    def get_job(self, job_id: str) -> Job | None:
        """Load a single job by ID."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        """Return jobs ordered by creation date (newest first)."""
        query = "SELECT * FROM jobs"
        params: list = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if deleted."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0

    def delete_all_jobs(self) -> int:
        """Delete every job. Returns count deleted."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM jobs")
        return cursor.rowcount

    def count_jobs(self, status: JobStatus | None = None) -> int:
        """Count jobs, optionally filtered by status."""
        query = "SELECT COUNT(*) FROM jobs"
        params: list = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------ #
    # Search                                                               #
    # ------------------------------------------------------------------ #

    def search_transcripts(self, query: str, limit: int = 50) -> list[Job]:
        """Full-text search across transcript text."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE full_text LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        segments: list[TranscriptSegment] = []
        if row["segments_json"]:
            raw = json.loads(row["segments_json"])
            segments = [
                TranscriptSegment(
                    start=s["start"],
                    end=s["end"],
                    text=s["text"],
                    confidence=s.get("confidence", 0.0),
                    speaker=s.get("speaker"),
                )
                for s in raw
            ]

        result: TranscriptionResult | None = None
        if row["full_text"]:
            result = TranscriptionResult(
                full_text=row["full_text"],
                segments=segments,
                language=row["language"] or "en",
                duration_seconds=row["duration_s"] or 0.0,
                provider=row["provider"] or "",
                model=row["model"] or "",
                audio_file=row["source_path"],
            )

        return Job(
            id=row["id"],
            file_path=row["source_path"],
            file_name=Path(row["source_path"]).name,
            status=JobStatus(row["status"]),
            provider=row["provider"] or "",
            model=row["model"] or "",
            language=row["language"] or "auto",
            progress_percent=row["progress"] or 0.0,
            error_message=row["error_message"] or "",
            created_at=row["created_at"],
            started_at=row["started_at"] or "",
            completed_at=row["completed_at"] or "",
            cost_actual=row["cost"] or 0.0,
            transcript_path=row["output_path"] or "",
            result=result,
        )
