"""Search engine orchestrator: manages rate limits, task execution, caching, and recovery."""

import concurrent.futures
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable

from vusca.models.flight import FlightLegOffer, Itinerary
from vusca.models.search import SearchJob, SearchLegTask, JobStatus
from vusca.providers.base import BaseFlightProvider
from vusca.core.db import DatabaseManager
from vusca.core.combinator import RouteCombinator, RouteBlueprint
from vusca import config

logger = logging.getLogger(__name__)


class SearchEngine:
    """Orchestrates flight leg queries, applies caching, and manages job execution."""

    def __init__(
        self,
        provider: BaseFlightProvider,
        db: Optional[DatabaseManager] = None,
        query_delay: float = config.DEFAULT_API_DELAY_SECONDS,
        max_retries: int = 3,
        concurrency: int = config.SEARCH_CONCURRENCY,
    ):
        self.provider = provider
        self.db = db or DatabaseManager()
        self.query_delay = query_delay
        self.max_retries = max_retries
        self.concurrency = max(1, concurrency)
        self._lock = threading.Lock()
        self._completed_count = 0

    def execute_job(
        self,
        job: SearchJob,
        blueprints: List[RouteBlueprint],
        progress_callback: Optional[Callable[[SearchLegTask, int, int], None]] = None,
        max_scales_per_direction: int = 2,
        max_stops_per_leg: int = 1,
    ) -> List[Itinerary]:
        """
        Executes all pending tasks in the job.
        Can resume jobs that were previously paused or partially completed.
        Supports concurrent execution when concurrency > 1.
        """
        job.status = JobStatus.IN_PROGRESS
        job.update_progress()
        self.db.save_job(job)

        offers_by_key: Dict[str, List[FlightLegOffer]] = {}
        total = len(job.tasks)
        self._completed_count = 0

        def _process_task(task: SearchLegTask):
            key = f"{task.origin}:{task.destination}:{task.travel_date.isoformat()}"

            # Check previous run completion or DB cache
            t_cache_start = time.time()
            cached = self.db.get_cached_offers(task.origin, task.destination, task.travel_date)
            if cached is not None:
                offers_by_key[key] = cached
                task.status = "CACHED"
                task.results_count = len(cached)
                task.provider_name = "SQLite DB"
                task.elapsed_seconds = round(time.time() - t_cache_start, 3)
                task.min_price_eur = min((o.price_eur for o in cached), default=None) if cached else None
                with self._lock:
                    self._completed_count += 1
                    current = self._completed_count
                    if current % 20 == 0:
                        job.update_progress()
                        self.db.save_job(job)
                    if progress_callback:
                        progress_callback(task, current, total)
                return

            # Need to query external provider
            t_ext_start = time.time()
            success = False
            for attempt in range(1, self.max_retries + 1):
                try:
                    time.sleep(self.query_delay)
                    t_api_start = time.time()
                    offers = self.provider.search_leg(
                        origin=task.origin,
                        destination=task.destination,
                        travel_date=task.travel_date,
                    )
                    api_duration = round(time.time() - t_api_start, 2)
                    offers_by_key[key] = offers
                    task.status = "SUCCESS"
                    task.results_count = len(offers)
                    task.provider_name = self.provider.name
                    task.elapsed_seconds = api_duration
                    task.min_price_eur = min((o.price_eur for o in offers), default=None) if offers else None
                    task.error_message = None
                    self.db.save_cached_offers(
                        task.origin, task.destination, task.travel_date, self.provider.name, offers
                    )
                    success = True
                    break
                except Exception as e:
                    task.retries += 1
                    err_msg = str(e)
                    task.error_message = err_msg
                    logger.warning(
                        f"Attempt {attempt}/{self.max_retries} failed for {key}: {err_msg}"
                    )
                    backoff = min(2 ** attempt, 15)
                    time.sleep(backoff)

            if not success:
                task.status = "FAILED"
                task.provider_name = self.provider.name
                task.elapsed_seconds = round(time.time() - t_ext_start, 2)
                offers_by_key[key] = []

            with self._lock:
                self._completed_count += 1
                current = self._completed_count
                if current % 10 == 0:
                    job.update_progress()
                    self.db.save_job(job)
                if progress_callback:
                    progress_callback(task, current, total)

        if self.concurrency > 1 and total > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                list(executor.map(_process_task, job.tasks))
        else:
            for t in job.tasks:
                _process_task(t)

        # Assemble itineraries from blueprints and collected offers
        itineraries = RouteCombinator.assemble_itineraries(
            blueprints,
            offers_by_key,
            max_scales_per_direction=max_scales_per_direction,
            max_stops_per_leg=max_stops_per_leg,
        )
        job.itineraries = itineraries
        job.status = JobStatus.COMPLETED
        job.update_progress()
        self.db.save_job(job)

        return itineraries
