"""Run exhaustive search for Malaysia with duration of at least 21 days (Semana Santa 2027)."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from vusca.models.calendar import PTOWindow
from vusca.core.combinator import RouteCombinator
from vusca.models.search import SearchJob, JobStatus
from vusca.core.search_engine import SearchEngine
from vusca.core.db import DatabaseManager
from vusca.agents.synthesis_agent import SynthesisAgent
from vusca.agents.route_agent import GLOBAL_HUBS, RouteAgent
from vusca.agents.pto_agent import PTOAgent
from vusca.providers.google_flights import GoogleFlightsProvider
from vusca.providers.mock import MockFlightProvider
from vusca.providers.pool import MultiProviderPool
from vusca import config

def main():
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    print(f"=== Starting Exhaustive 21+ Days Search: Malaysia & Singapore [{job_id}] ===")

    # Windows of at least 21 days
    windows = [
        PTOWindow(
            start_date=date(2027, 3, 15),
            end_date=date(2027, 4, 4),
            total_days=21,
            work_days_needed=12,
            weekend_days=6,
            holiday_days=3,
            efficiency_ratio=2.25,
            summary="Exacto 21 días: San José + Semana Santa (21d totales con 12d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 6),
            end_date=date(2027, 3, 28),
            total_days=23,
            work_days_needed=12,
            weekend_days=8,
            holiday_days=3,
            efficiency_ratio=2.42,
            summary="23 días: Marzo previo a Semana Santa (23d totales con 12d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 12),
            end_date=date(2027, 4, 4),
            total_days=24,
            work_days_needed=13,
            weekend_days=8,
            holiday_days=3,
            efficiency_ratio=2.35,
            summary="24 días: Semana Santa central (24d totales con 13d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 19),
            end_date=date(2027, 4, 11),
            total_days=24,
            work_days_needed=13,
            weekend_days=8,
            holiday_days=3,
            efficiency_ratio=2.35,
            summary="24 días: Semana Santa y Pascua posterior (24d totales con 13d PTO)",
        ),
    ]

    origins = ["MAD", "BIO"]
    destinations = ["KUL", "SIN"]
    return_destinations = ["KUL", "SIN"]
    candidate_stopovers = ["DOH", "DXB", "AUH", "IST", "BKK", "ICN", "HKG"]

    stopover_names = {c: GLOBAL_HUBS.get(c, {}).get("name", c) for c in candidate_stopovers}
    stopover_names["KUL"] = "Kuala Lumpur"
    stopover_names["SIN"] = "Singapur"

    combinator = RouteCombinator(
        candidate_windows=windows,
        origins=origins,
        destinations=destinations,
        candidate_stopovers=candidate_stopovers,
        min_stopover_days=2,
        max_stopover_days=4,
        return_destinations=return_destinations,
        include_dual_stopovers=True,
    )
    blueprints, tasks = combinator.generate_blueprints()
    print(f"Generated {len(blueprints)} blueprints (all >= 21 days) and {len(tasks)} unique atomic tasks.")

    db = DatabaseManager()

    # Provider setup: use official provider from configuration (no mock fallback in real searches)
    provider = get_flight_provider()

    search_job = SearchJob(
        job_id=job_id,
        origin=", ".join(origins),
        final_destination=", ".join(destinations),
        status=JobStatus.PENDING,
        country="ES",
        subdivision="MD",
        max_pto_days=13,
        preferred_month="3",
        return_destinations=return_destinations,
        candidate_windows=windows,
        candidate_stopovers=candidate_stopovers,
        stopover_names=stopover_names,
        tasks=tasks,
    )
    db.save_job(search_job)

    print(f"Executing search with {config.SEARCH_CONCURRENCY} concurrency and {config.DEFAULT_API_DELAY_SECONDS}s delay...")
    engine = SearchEngine(
        provider=provider,
        db=db,
        query_delay=config.DEFAULT_API_DELAY_SECONDS,
        concurrency=config.SEARCH_CONCURRENCY,
    )

    def progress_cb(task, current, total):
        if current % 25 == 0 or current == total:
            print(f"Progress: [{current}/{total}] ({(current*100/total):.1f}%) - {task.origin}->{task.destination} ({task.status})", flush=True)

    itineraries = engine.execute_job(
        job=search_job,
        blueprints=blueprints,
        progress_callback=progress_cb,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )
    print(f"Assembled {len(itineraries)} complete itineraries.")

    # Filter strictly for itineraries with >= 21 days
    valid_21d = [it for it in itineraries if it.total_trip_days >= 21]
    print(f"Valid itineraries with total_trip_days >= 21: {len(valid_21d)}")

    # Synthesis & AI report
    synthesis = SynthesisAgent()
    route_agent = RouteAgent()
    pto_agent = PTOAgent(country="ES", subdivision="MD")

    search_context = {
        "priority": "balanced",
        "origins": origins,
        "destinations": destinations,
        "return_destinations": return_destinations,
        "stopovers": candidate_stopovers,
        "stopover_names": stopover_names,
        "pto_strategy": pto_agent.get_strategy_rationale(windows),
        "hub_strategy": route_agent.get_hub_strategy_explanation(candidate_stopovers),
        "open_jaw_strategy": route_agent.get_open_jaw_strategy(destinations, return_destinations),
        "constraints": {
            "min_total_days": 21,
            "max_scales": 2,
            "max_stops_per_leg": 1,
            "max_pto_days": 13,
        },
        "stats": {
            "total_blueprints": len(blueprints),
            "total_leg_tasks": len(tasks),
        },
    }

    print("Generating comprehensive executive synthesis report...")
    report_md = synthesis.generate_final_report(
        origin=search_job.origin,
        destination=search_job.final_destination,
        itineraries=valid_21d,
        candidate_stopover_names=stopover_names,
        search_context=search_context,
    )

    search_job.ai_final_analysis = report_md
    db.save_job(search_job)

    out_file = "reporte_MALASIA_21_DIAS_2027.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Report saved to {out_file} (Length: {len(report_md)} bytes).")
    print("=== Search & Synthesis Complete! ===")

if __name__ == "__main__":
    main()
