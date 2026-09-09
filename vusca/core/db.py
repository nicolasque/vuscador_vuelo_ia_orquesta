"""Database persistence and caching layer using SQLite."""

import json
import sqlite3
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
import os

from vusca.models.flight import FlightLegOffer
from vusca.models.search import SearchJob, SearchLegTask, JobStatus
from vusca import config


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class DatabaseManager:
    """Manages SQLite storage for leg search cache and job state."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.CACHE_DB_PATH
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            
            # Table for cached flight leg offers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cached_legs (
                    cache_key TEXT PRIMARY KEY,
                    origin TEXT,
                    destination TEXT,
                    travel_date TEXT,
                    provider TEXT,
                    offers_json TEXT,
                    created_at TIMESTAMP
                )
            """)

            # Table for long-running search jobs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT,
                    origin TEXT,
                    destination TEXT,
                    job_data_json TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)

            conn.commit()

    # -------------------------------------------------------------
    # Cached Legs
    # -------------------------------------------------------------
    def get_cached_offers(
        self, origin: str, destination: str, travel_date: date, ttl_hours: Optional[int] = None
    ) -> Optional[List[FlightLegOffer]]:
        ttl = ttl_hours if ttl_hours is not None else config.CACHE_TTL_HOURS
        cache_key = f"{origin.upper()}:{destination.upper()}:{travel_date.isoformat()}"
        cutoff = now_utc() - timedelta(hours=ttl)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT offers_json, created_at FROM cached_legs
                WHERE cache_key = ? AND created_at >= ?
                """,
                (cache_key, cutoff.isoformat()),
            )
            row = cursor.fetchone()
            if row:
                offers_data = json.loads(row["offers_json"])
                return [FlightLegOffer(**item) for item in offers_data]
        return None

    def save_cached_offers(
        self, origin: str, destination: str, travel_date: date, provider: str, offers: List[FlightLegOffer]
    ):
        cache_key = f"{origin.upper()}:{destination.upper()}:{travel_date.isoformat()}"
        now_str = now_utc().isoformat()
        offers_json = json.dumps([o.model_dump(mode="json") for o in offers])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cached_legs 
                (cache_key, origin, destination, travel_date, provider, offers_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    origin.upper(),
                    destination.upper(),
                    travel_date.isoformat(),
                    provider,
                    offers_json,
                    now_str,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # Search Job Management (Pause & Resume)
    # -------------------------------------------------------------
    def save_job(self, job: SearchJob):
        job.updated_at = now_utc()
        job_data_json = job.model_dump_json()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO search_jobs
                (job_id, status, origin, destination, job_data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.status.value,
                    job.origin,
                    job.final_destination,
                    job_data_json,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[SearchJob]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_data_json FROM search_jobs WHERE job_id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
            if row:
                return SearchJob.model_validate_json(row["job_data_json"])
        return None

    def list_jobs(self, limit: int = 10) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, status, origin, destination, created_at, updated_at
                FROM search_jobs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
