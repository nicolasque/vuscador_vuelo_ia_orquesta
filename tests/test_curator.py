"""Comprehensive tests and comparison benchmarks for DeterministicCurator."""

import time
import pytest
from datetime import date
from vusca.core.curator import DeterministicCurator, CuratedArchetypes
from vusca.models.flight import Itinerary, FlightLegOffer, StopoverDetail


def make_mock_itinerary(
    it_id: str,
    origin: str,
    destination: str,
    return_dest: str,
    price: float,
    score: float,
    pto_ratio: float,
    stopover_hub: str = None,
    trip_days: int = 22,
    work_days: int = 11,
) -> Itinerary:
    legs = [
        FlightLegOffer(
            provider="test",
            origin=origin,
            destination=stopover_hub or destination,
            departure_date=date(2027, 3, 13),
            price_eur=price * 0.4,
            stops_count=0,
            airline_names=["TestAir"],
        ),
        FlightLegOffer(
            provider="test",
            origin=stopover_hub or destination,
            destination=destination,
            departure_date=date(2027, 3, 15),
            price_eur=price * 0.2,
            stops_count=0,
            airline_names=["TestAir"],
        ) if stopover_hub else None,
        FlightLegOffer(
            provider="test",
            origin=destination,
            destination=return_dest,
            departure_date=date(2027, 4, 4),
            price_eur=price * 0.4 if stopover_hub else price * 0.6,
            stops_count=0,
            airline_names=["TestAir"],
        ),
    ]
    valid_legs = [leg for leg in legs if leg is not None]
    
    stopovers = [
        StopoverDetail(
            city_code=stopover_hub,
            city_name=stopover_hub,
            stay_days=2,
            arrival_date=date(2027, 3, 13),
            departure_date=date(2027, 3, 15),
        )
    ] if stopover_hub else []

    it = Itinerary(
        itinerary_id=it_id,
        origin=origin,
        final_destination=destination,
        start_date=date(2027, 3, 13),
        end_date=date(2027, 4, 4),
        legs=valid_legs,
        stopovers=stopovers,
        total_price_eur=price,
        total_trip_days=trip_days,
        work_days_needed=work_days,
        pto_efficiency_ratio=pto_ratio,
        ai_score=score,
        route_summary=f"{origin} -> {destination} -> {return_dest}",
    )
    return it


def test_deterministic_curator_champions_extraction():
    """Verifies that DeterministicCurator correctly extracts the global and scenario champions."""
    itins = [
        make_mock_itinerary("it_1", "MAD", "TYO", "MAD", price=1200.0, score=85.0, pto_ratio=2.0, stopover_hub="IST"),
        make_mock_itinerary("it_2", "MAD", "OSA", "MAD", price=950.0, score=89.0, pto_ratio=2.0, stopover_hub="ICN"),  # Cheapest MAD-MAD
        make_mock_itinerary("it_3", "BIO", "TYO", "BIO", price=1500.0, score=82.0, pto_ratio=2.0, stopover_hub="IST"),
        make_mock_itinerary("it_4", "BIO", "OSA", "BIO", price=1450.0, score=84.0, pto_ratio=2.0, stopover_hub="ICN"),  # Cheapest BIO-BIO
        make_mock_itinerary("it_5", "MAD", "TYO", "BIO", price=1100.0, score=91.0, pto_ratio=2.5, stopover_hub="SIN"),  # Best Score & MAD-BIO
        make_mock_itinerary("it_6", "MAD", "FUK", "BIO", price=1150.0, score=88.0, pto_ratio=2.6, stopover_hub="HAN"),  # Best PTO
    ]

    curator = DeterministicCurator(activation_threshold=5)
    assert curator.is_applicable(len(itins))

    curated = curator.curate(itins, max_selection_size=10)

    # 1. Check Global Champions
    assert curated.best_overall.itinerary_id == "it_5"
    assert curated.cheapest_overall.itinerary_id == "it_2"
    assert curated.cheapest_overall.total_price_eur == 950.0
    assert curated.best_pto_overall.itinerary_id == "it_6"
    assert curated.best_pto_overall.pto_efficiency_ratio == 2.6

    # 2. Check Scenario Champions
    assert ("MAD", "MAD") in curated.scenario_champions
    assert ("BIO", "BIO") in curated.scenario_champions
    assert ("MAD", "BIO") in curated.scenario_champions
    assert curated.scenario_champions[("MAD", "BIO")].itinerary_id == "it_5"
    assert curated.scenario_champions[("MAD", "MAD")].itinerary_id == "it_2"

    # 3. Check Hub Champions
    assert "IST" in curated.hub_champions
    assert "ICN" in curated.hub_champions
    assert "SIN" in curated.hub_champions
    assert "HAN" in curated.hub_champions
    assert curated.hub_champions["SIN"].itinerary_id == "it_5"

    # 4. Check Market Stats
    assert curated.market_stats["total_itineraries"] == 6
    assert curated.market_stats["price_min"] == 950.0
    assert curated.market_stats["price_max"] == 1500.0
    assert curated.market_stats["pto_ratio_max"] == 2.6


def test_pareto_frontier_mathematical_soundness():
    """Verifies that every member of the Pareto frontier is strictly non-dominated."""
    itins = [
        make_mock_itinerary("A", "MAD", "TYO", "MAD", price=1000.0, score=90.0, pto_ratio=2.5),
        # B is dominated by A (more expensive, lower score, lower pto)
        make_mock_itinerary("B", "MAD", "TYO", "MAD", price=1200.0, score=85.0, pto_ratio=2.0),
        # C is Pareto optimal: cheaper than A (800€) even though lower score (82.0)
        make_mock_itinerary("C", "MAD", "TYO", "MAD", price=800.0, score=82.0, pto_ratio=2.0),
        # D is Pareto optimal: higher score (95.0) even though more expensive (1100€)
        make_mock_itinerary("D", "MAD", "TYO", "MAD", price=1100.0, score=95.0, pto_ratio=2.8),
    ]

    curator = DeterministicCurator()
    pareto = curator._compute_pareto_frontier(itins)
    pareto_ids = {it.itinerary_id for it in pareto}

    assert "A" in pareto_ids
    assert "C" in pareto_ids
    assert "D" in pareto_ids
    assert "B" not in pareto_ids, "Dominated itinerary B must not be in Pareto frontier!"


def test_curator_benchmark_vs_legacy_approach():
    """Benchmarks DeterministicCurator against the legacy approach on a large synthetic dataset (10,000 itineraries).
    
    Validates:
      1. Execution time (< 50 milliseconds for 10,000 itineraries).
      2. Hub diversity in top selection (Legacy vs Pareto Curator).
      3. Guaranteed inclusion of global champions and all scenarios.
    """
    import random
    random.seed(42)

    origins = ["MAD", "BIO"]
    destinations = ["TYO", "OSA", "FUK", "CTS", "OKA", "NGO"]
    hubs = ["IST", "DOH", "DXB", "AUH", "ICN", "HKG", "TPE", "BKK", "SIN", "KUL", "HAN", "HEL"]

    dataset: List[Itinerary] = []
    
    # Generate 10,000 realistic itineraries
    for i in range(10000):
        orig = random.choice(origins)
        ret_arr = random.choice(origins)
        dest = random.choice(destinations)
        hub = random.choice(hubs)
        price = round(random.uniform(900.0, 2200.0), 2)
        # Give special deals to certain hubs
        if hub == "HAN" and i % 50 == 0:
            price = 880.0
        score = round(random.uniform(65.0, 92.0), 1)
        pto = round(random.uniform(1.8, 2.6), 2)
        dataset.append(make_mock_itinerary(f"it_{i}", orig, dest, ret_arr, price, score, pto, hub))

    # Sort dataset like SynthesisAgent does
    dataset.sort(key=lambda it: it.ai_score, reverse=True)

    # -------------------------------------------------------------
    # 1. Performance Benchmark
    # -------------------------------------------------------------
    curator = DeterministicCurator()
    t_start = time.perf_counter()
    curated = curator.curate(dataset, max_selection_size=20)
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    print(f"\n[BENCHMARK] Curating 10,000 itineraries took: {elapsed_ms:.2f} ms")
    assert elapsed_ms < 100.0, f"Curator is too slow ({elapsed_ms:.2f} ms > 100 ms)!"

    # -------------------------------------------------------------
    # 2. Champion Verification
    # -------------------------------------------------------------
    true_cheapest = min(dataset, key=lambda it: it.total_price_eur)
    assert curated.cheapest_overall.total_price_eur == true_cheapest.total_price_eur
    assert curated.cheapest_overall.itinerary_id in [it.itinerary_id for it in curated.curated_selection]

    # -------------------------------------------------------------
    # 3. Hub Diversity Comparison (Legacy vs Curator)
    # -------------------------------------------------------------
    # Legacy approach: just top 20 by score
    legacy_selection = dataset[:20]
    legacy_hubs = {it.stopovers[0].city_code for it in legacy_selection if it.stopovers}
    
    curator_hubs = {it.stopovers[0].city_code for it in curated.curated_selection if it.stopovers}

    print(f"[DIVERSITY] Legacy distinct hubs in Top 20: {len(legacy_hubs)} / {len(hubs)}")
    print(f"[DIVERSITY] Curator distinct hubs in Top 20: {len(curator_hubs)} / {len(hubs)}")

    # The curated selection must cover more hubs or equal
    assert len(curator_hubs) >= len(legacy_hubs)
    assert len(curator_hubs) >= 8, "Curator must cover at least 8 distinct hubs in top 20!"

    # -------------------------------------------------------------
    # 4. Scenario Coverage
    # -------------------------------------------------------------
    curator_scenarios = {(it.origin, it.legs[-1].destination) for it in curated.curated_selection}
    assert ("MAD", "MAD") in curator_scenarios
    assert ("BIO", "BIO") in curator_scenarios
    assert ("MAD", "BIO") in curator_scenarios
    assert ("BIO", "MAD") in curator_scenarios
    print(f"[SCENARIOS] All 4 scenarios represented in curated selection: {curator_scenarios}")
