"""Crash-safe durable job replay proof."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass


class SimulatedWorkerCrash(Exception):
    """A worker stopped after a committed item checkpoint."""


@dataclass(frozen=True)
class JobResult:
    processed: int
    skipped: int
    state: str


class DurableJobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.executescript(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                checkpoint INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE job_items (
                job_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                PRIMARY KEY (job_id, item_key)
            );
            """
        )

    def ensure_job(self, job_id: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO jobs (job_id, state) VALUES (?, 'queued')", (job_id,)
        )

    def begin(self, job_id: str) -> None:
        self.connection.execute("UPDATE jobs SET state = 'running' WHERE job_id = ?", (job_id,))
        self.connection.commit()

    def mark_item(self, job_id: str, item_key: str) -> bool:
        result = self.connection.execute(
            "INSERT OR IGNORE INTO job_items VALUES (?, ?)", (job_id, item_key)
        )
        self.connection.commit()
        return result.rowcount == 1

    def finish(self, job_id: str, state: str) -> None:
        self.connection.execute("UPDATE jobs SET state = ? WHERE job_id = ?", (state, job_id))
        self.connection.commit()

    def state(self, job_id: str) -> str:
        return self.connection.execute(
            "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()[0]

    def item_count(self, job_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM job_items WHERE job_id = ?", (job_id,)
        ).fetchone()[0]


def run_job(
    repository: DurableJobRepository,
    job_id: str,
    items: Iterable[str],
    crash_after: int | None = None,
) -> JobResult:
    repository.ensure_job(job_id)
    repository.begin(job_id)
    processed = 0
    skipped = 0
    for item_key in items:
        if not repository.mark_item(job_id, item_key):
            skipped += 1
            continue
        processed += 1
        if crash_after is not None and processed == crash_after:
            raise SimulatedWorkerCrash(job_id)
    repository.finish(job_id, "succeeded")
    return JobResult(processed=processed, skipped=skipped, state="succeeded")
