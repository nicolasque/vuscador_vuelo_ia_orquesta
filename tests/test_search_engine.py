"""Tests for SearchEngine and DB caching/resilience."""

import os
import tempfile
from datetime import date
from vusca.models.calendar import PTOWindow
from vusca.models.search import SearchJob, SearchLegTask, JobStatus
from vusca.providers.mock import MockFlightProvider
from vusca.core.db import DatabaseManager
from vusca.core.combinator import RouteCombinator
from vusca.core.search_engine import SearchEngine


def test_search_engine_execution_and_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_vusca.db")
        db = DatabaseManager(db_path=db_path)
        provider = MockFlightProvider()
        engine = SearchEngine(provider=provider, db=db, query_delay=0.01)

        window = PTOWindow(
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 18),
            total_days=9,
            work_days_needed=4,
            weekend_days=4,
            holiday_days=1,
            efficiency_ratio=2.25,
        )

        combinator = RouteCombinator(
            origin="MAD",
            destination="TYO",
            candidate_windows=[window],
            candidate_stopovers=["IST"],
            stopover_names={"IST": "Estambul"},
            min_stopover_days=1,
            max_stopover_days=2,
        )

        blueprints, tasks = combinator.generate_blueprints()

        job = SearchJob(
            job_id="test_job_1",
            origin="MAD",
            final_destination="TYO",
            tasks=tasks,
        )

        itineraries = engine.execute_job(job, blueprints)

        assert len(itineraries) > 0
        assert job.status == JobStatus.COMPLETED
        assert job.completed_task_count == len(tasks)

        # Verify items are in SQLite cache
        t0 = tasks[0]
        cached = db.get_cached_offers(t0.origin, t0.destination, t0.travel_date)
        assert cached is not None
        assert len(cached) > 0

        # Now test a second run with new pending tasks for the same route: all should be resolved as CACHED
        fresh_tasks = [
            SearchLegTask(
                task_id=f"new_{t.task_id}",
                origin=t.origin,
                destination=t.destination,
                travel_date=t.travel_date,
            )
            for t in tasks
        ]
        job2 = SearchJob(
            job_id="test_job_2",
            origin="MAD",
            final_destination="TYO",
            tasks=fresh_tasks,
        )
        engine.execute_job(job2, blueprints)
        for t in job2.tasks:
            assert t.status == "CACHED"
