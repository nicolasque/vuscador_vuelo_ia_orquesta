"""Run exhaustive Easter 2027 search for Malaysia and Singapore."""

import os
import sys
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
    print(f"=== Starting Exhaustive Easter 2027 Search: Malaysia & Singapore [{job_id}] ===")

    # 1. Candidate windows around Semana Santa 2027
    windows = [
        PTOWindow(
            start_date=date(2027, 3, 19),
            end_date=date(2027, 3, 28),
            total_days=10,
            work_days_needed=3,
            weekend_days=4,
            holiday_days=3,
            efficiency_ratio=3.33,
            summary="San José + Semana Santa (10d totales con 3d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 20),
            end_date=date(2027, 3, 29),
            total_days=10,
            work_days_needed=4,
            weekend_days=4,
            holiday_days=2,
            efficiency_ratio=2.50,
            summary="Semana Santa + Lunes de Pascua (10d totales con 4d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 24),
            end_date=date(2027, 4, 4),
            total_days=12,
            work_days_needed=6,
            weekend_days=4,
            holiday_days=2,
            efficiency_ratio=2.00,
            summary="Semana Santa + Pascua extendida (12d totales con 6d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 25),
            end_date=date(2027, 4, 4),
            total_days=11,
            work_days_needed=5,
            weekend_days=4,
            holiday_days=2,
            efficiency_ratio=2.20,
            summary="Jueves Santo a Domingo de Pascua (11d totales con 5d PTO)",
        ),
        PTOWindow(
            start_date=date(2027, 3, 19),
            end_date=date(2027, 4, 4),
            total_days=17,
            work_days_needed=8,
            weekend_days=6,
            holiday_days=3,
            efficiency_ratio=2.12,
            summary="Quincena Completa de Pascua (17d totales con 8d PTO)",
        ),
    ]

    origins = ["MAD", "BIO"]
    destinations = ["KUL", "SIN"]
    return_destinations = ["KUL", "SIN"]
    candidate_stopovers = ["DOH", "DXB", "AUH", "IST", "BKK", "ICN", "HKG", "TPE"]

    stopover_names = {c: GLOBAL_HUBS.get(c, {}).get("name", c) for c in candidate_stopovers}
    stopover_names["KUL"] = "Kuala Lumpur"
    stopover_names["SIN"] = "Singapur"

    combinator = RouteCombinator(
        candidate_windows=windows,
        origins=origins,
        destinations=destinations,
        candidate_stopovers=candidate_stopovers,
        min_stopover_days=1,
        max_stopover_days=3,
        return_destinations=return_destinations,
        include_dual_stopovers=True,
    )
    blueprints, tasks = combinator.generate_blueprints()
    print(f"Generated {len(blueprints)} blueprints and {len(tasks)} unique atomic tasks.")

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
        max_pto_days=8,
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
        if current % 20 == 0 or current == total:
            print(f"Progress: [{current}/{total}] ({(current*100/total):.1f}%) - {task.origin}->{task.destination} ({task.status})")

    itineraries = engine.execute_job(
        job=search_job,
        blueprints=blueprints,
        progress_callback=progress_cb,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )
    print(f"Assembled {len(itineraries)} complete itineraries.")

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
            "max_scales": 2,
            "max_stops_per_leg": 1,
            "max_pto_days": 8,
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
        itineraries=itineraries,
        candidate_stopover_names=stopover_names,
        search_context=search_context,
    )

    search_job.ai_final_analysis = report_md
    db.save_job(search_job)

    out_file = "reporte_MAD_BIO_MALASIA_SINGAPUR_2027.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Report saved to {out_file} (Length: {len(report_md)} bytes).")
    print("=== Search & Synthesis Complete! ===")

if __name__ == "__main__":
    main()
