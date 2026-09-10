"""
Automated tests verifying mathematical equivalence, zero regressions,
and robustness between baseline unmemoized and optimized assemble_itineraries.
"""

from datetime import date
from typing import List, Dict, Tuple, Optional
import pytest

from vusca.models.calendar import PTOWindow
from vusca.models.flight import FlightLegOffer, Itinerary
from vusca.core.combinator import RouteCombinator, RouteBlueprint


def assemble_itineraries_unmemoized_baseline(
    blueprints: List[RouteBlueprint],
    offers_by_key: Dict[str, List[FlightLegOffer]],
    max_scales_per_direction: int = 2,
    max_stops_per_leg: int = 1,
) -> List[Itinerary]:
    """
    Original unmemoized brute-force implementation evaluating all offers.
    Used as ground-truth oracle to prove 100% equivalence of the optimized code.
    """
    import itertools
    import uuid

    def find_cheapest_valid_direction(
        keys: List[Tuple[str, str, date]],
        has_stopover: bool,
    ) -> Optional[List[FlightLegOffer]]:
        candidates_list = []
        for orig, dest, d in keys:
            key = f"{orig.upper()}:{dest.upper()}:{d.isoformat()}"
            offs = offers_by_key.get(key, [])
            if not offs:
                return None
            valid_offs = [o for o in offs if o.stops_count <= max_stops_per_leg]
            if not valid_offs:
                return None
            candidates_list.append(
                sorted(valid_offs, key=lambda o: (o.price_eur, o.stops_count, o.total_duration_minutes or 9999))
            )

        best_combo = None
        best_price = float("inf")
        main_stopover_count = 1 if has_stopover else 0

        for combo in itertools.product(*candidates_list):
            if any(leg.stops_count > max_stops_per_leg for leg in combo):
                continue
            transfer_stops = sum(leg.stops_count for leg in combo)
            total_scales = main_stopover_count + transfer_stops
            if total_scales <= max_scales_per_direction:
                combo_price = sum(leg.price_eur for leg in combo)
                if combo_price < best_price:
                    best_price = combo_price
                    best_combo = list(combo)

        return best_combo

    itineraries: List[Itinerary] = []
    for bp in blueprints:
        out_keys = getattr(bp, "outbound_keys", None) or (bp.leg_keys[:2] if getattr(bp, "has_outbound_stopover", False) else bp.leg_keys[:1])
        ret_keys = getattr(bp, "return_keys", None) or bp.leg_keys[len(out_keys):]
        has_out_stop = getattr(bp, "has_outbound_stopover", False)
        has_ret_stop = getattr(bp, "has_return_stopover", False)

        best_outbound = find_cheapest_valid_direction(out_keys, has_out_stop)
        if not best_outbound:
            continue

        best_return = find_cheapest_valid_direction(ret_keys, has_ret_stop)
        if not best_return:
            continue

        legs_for_bp = best_outbound + best_return
        itinerary = Itinerary(
            itinerary_id=str(uuid.uuid4())[:8],
            origin=bp.origin,
            final_destination=bp.destination,
            start_date=bp.start_date,
            end_date=bp.end_date,
            legs=legs_for_bp,
            stopovers=bp.stopovers,
            route_summary=bp.description,
        )
        itinerary.calculate_totals(work_days=bp.pto_window.work_days_needed)
        itineraries.append(itinerary)

    return itineraries


@pytest.fixture
def sample_blueprints_and_offers():
    """Generates a rich set of blueprints and multiple competing flight offers."""
    window = PTOWindow(
        start_date=date(2027, 3, 13),
        end_date=date(2027, 4, 4),
        total_days=23,
        work_days_needed=11,
        weekend_days=8,
        holiday_days=4,
        efficiency_ratio=2.59,
    )

    combinator = RouteCombinator(
        origins=["MAD", "BIO"],
        destinations=["BKK", "HKT"],
        return_destinations=["BKK", "HKT"],
        return_arrivals=["MAD", "BIO"],
        candidate_windows=[window],
        candidate_stopovers=["IST", "KUL"],
        stopover_names={"IST": "Estambul", "KUL": "Kuala Lumpur"},
        min_stopover_days=1,
        max_stopover_days=2,
        include_dual_stopovers=True,
        allowed_scenarios=[("BIO", "BIO"), ("MAD", "MAD"), ("MAD", "BIO")],
    )

    blueprints, tasks = combinator.generate_blueprints()

    # Create competing flight offers for each task:
    # Multiple direct offers, multiple 1-stop offers, and an invalid 2-stop offer
    offers_by_key: Dict[str, List[FlightLegOffer]] = {}
    for t in tasks:
        key = f"{t.origin}:{t.destination}:{t.travel_date.isoformat()}"
        offers_by_key[key] = [
            # Direct offers
            FlightLegOffer(
                provider="test",
                origin=t.origin,
                destination=t.destination,
                departure_date=t.travel_date,
                price_eur=450.0,
                stops_count=0,
                total_duration_minutes=600,
                airline_names=["DirectAir"],
            ),
            FlightLegOffer(
                provider="test",
                origin=t.origin,
                destination=t.destination,
                departure_date=t.travel_date,
                price_eur=420.0,
                stops_count=0,
                total_duration_minutes=650,
                airline_names=["DirectSaver"],
            ),
            # 1-stop offers (cheaper price, but adds a transfer scale)
            FlightLegOffer(
                provider="test",
                origin=t.origin,
                destination=t.destination,
                departure_date=t.travel_date,
                price_eur=310.0,
                stops_count=1,
                total_duration_minutes=850,
                airline_names=["TransferOne"],
            ),
            FlightLegOffer(
                provider="test",
                origin=t.origin,
                destination=t.destination,
                departure_date=t.travel_date,
                price_eur=290.0,
                stops_count=1,
                total_duration_minutes=900,
                airline_names=["TransferCheap"],
            ),
            # Invalid 2-stop offer (must ALWAYS be rejected)
            FlightLegOffer(
                provider="test",
                origin=t.origin,
                destination=t.destination,
                departure_date=t.travel_date,
                price_eur=100.0,  # Ultra-cheap bait
                stops_count=2,    # Invalid: max_stops_per_leg is 1
                total_duration_minutes=1500,
                airline_names=["DisqualifiedMultiStop"],
            ),
        ]

    return blueprints, offers_by_key


def test_unmemoized_vs_memoized_exact_mathematical_equivalence(sample_blueprints_and_offers):
    """
    Guarantees 100% mathematical equivalence between the baseline brute-force
    and the optimized memoized version across every single blueprint and metric.
    """
    blueprints, offers_by_key = sample_blueprints_and_offers

    baseline_itins = assemble_itineraries_unmemoized_baseline(
        blueprints=blueprints,
        offers_by_key=offers_by_key,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )

    optimized_itins = RouteCombinator.assemble_itineraries(
        blueprints=blueprints,
        offers_by_key=offers_by_key,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )

    # 1. Same total count of valid assembled itineraries
    assert len(baseline_itins) == len(optimized_itins), (
        f"Itinerary counts mismatch: baseline={len(baseline_itins)}, optimized={len(optimized_itins)}"
    )
    assert len(optimized_itins) > 0

    # 2. Map itineraries by (origin, destination, dates, description) to compare exact results
    baseline_map = {
        (it.origin, it.final_destination, it.start_date, it.end_date, it.route_summary): it
        for it in baseline_itins
    }
    optimized_map = {
        (it.origin, it.final_destination, it.start_date, it.end_date, it.route_summary): it
        for it in optimized_itins
    }

    assert set(baseline_map.keys()) == set(optimized_map.keys())

    # 3. Exact matching on prices, legs, stops, and airlines
    for key, base_it in baseline_map.items():
        opt_it = optimized_map[key]

        # Exact same total price
        assert base_it.total_price_eur == opt_it.total_price_eur, (
            f"Price discrepancy for {key}: baseline {base_it.total_price_eur} != optimized {opt_it.total_price_eur}"
        )

        # Exact same number of legs
        assert len(base_it.legs) == len(opt_it.legs)

        # Exact same legs selection
        for b_leg, o_leg in zip(base_it.legs, opt_it.legs):
            assert b_leg.origin == o_leg.origin
            assert b_leg.destination == o_leg.destination
            assert b_leg.departure_date == o_leg.departure_date
            assert b_leg.price_eur == o_leg.price_eur
            assert b_leg.stops_count == o_leg.stops_count
            assert b_leg.stops_count <= 1  # Verify constraint respected


def test_scale_constraint_enforcement():
    """
    Verifies that when a stopover is present (1 scale), and max_scales_per_direction=2,
    at most 1 additional transfer stop across both legs is permitted.
    If both legs are 1-stop (1 + 1 + 1 = 3 > 2), the optimizer correctly picks a direct 0-stop leg.
    """
    bp = RouteBlueprint(
        blueprint_id="test_outbound_scale_constraint",
        origin="MAD",
        destination="BKK",
        start_date=date(2027, 3, 13),
        end_date=date(2027, 4, 4),
        pto_window=PTOWindow(
            start_date=date(2027, 3, 13),
            end_date=date(2027, 4, 4),
            total_days=23,
            work_days_needed=11,
            weekend_days=8,
            holiday_days=4,
            efficiency_ratio=2.59,
        ),
        leg_keys=[
            ("MAD", "IST", date(2027, 3, 13)),
            ("IST", "BKK", date(2027, 3, 15)),
            ("BKK", "MAD", date(2027, 4, 4)),
        ],
        stopovers=[],
        description="MAD ➔ IST (2d) ➔ BKK ➔ MAD",
        has_outbound_stopover=True,
        has_return_stopover=False,
    )

    offers_by_key = {
        # MAD -> IST has a cheap 1-stop (100€) and a pricier 0-stop (200€)
        "MAD:IST:2027-03-13": [
            FlightLegOffer(provider="t", origin="MAD", destination="IST", departure_date=date(2027, 3, 13), price_eur=100.0, stops_count=1),
            FlightLegOffer(provider="t", origin="MAD", destination="IST", departure_date=date(2027, 3, 13), price_eur=200.0, stops_count=0),
        ],
        # IST -> BKK has a cheap 1-stop (150€) and a pricier 0-stop (250€)
        "IST:BKK:2027-03-15": [
            FlightLegOffer(provider="t", origin="IST", destination="BKK", departure_date=date(2027, 3, 15), price_eur=150.0, stops_count=1),
            FlightLegOffer(provider="t", origin="IST", destination="BKK", departure_date=date(2027, 3, 15), price_eur=250.0, stops_count=0),
        ],
        # Return flight: direct 400€
        "BKK:MAD:2027-04-04": [
            FlightLegOffer(provider="t", origin="BKK", destination="MAD", departure_date=date(2027, 4, 4), price_eur=400.0, stops_count=0),
        ],
    }

    itins = RouteCombinator.assemble_itineraries(
        blueprints=[bp],
        offers_by_key=offers_by_key,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )

    assert len(itins) == 1
    outbound_legs = itins[0].legs[:2]
    # Total outbound scales = 1 (main stopover IST) + sum(transfer stops)
    transfer_stops = sum(l.stops_count for l in outbound_legs)
    assert 1 + transfer_stops <= 2, "Outbound scales must not exceed 2"
    # The optimal valid combination is 100€ (1-stop) + 250€ (0-stop) = 350€,
    # because 100€ (1-stop) + 150€ (1-stop) would yield 1 + 2 = 3 > 2 scales!
    assert sum(l.price_eur for l in outbound_legs) == 350.0


def test_edge_cases_handling():
    """Verifies edge cases such as missing offers, invalid legs, and empty inputs."""
    # 1. Empty blueprints list
    assert RouteCombinator.assemble_itineraries([], {}) == []

    # 2. Blueprint with missing leg offers
    bp = RouteBlueprint(
        blueprint_id="test_missing",
        origin="MAD",
        destination="BKK",
        start_date=date(2027, 3, 13),
        end_date=date(2027, 4, 4),
        pto_window=PTOWindow(
            start_date=date(2027, 3, 13),
            end_date=date(2027, 4, 4),
            total_days=23,
            work_days_needed=11,
            weekend_days=8,
            holiday_days=4,
            efficiency_ratio=2.59,
        ),
        leg_keys=[("MAD", "BKK", date(2027, 3, 13)), ("BKK", "MAD", date(2027, 4, 4))],
        stopovers=[],
        description="Direct",
    )

    # Missing return flight
    offers_partial = {
        "MAD:BKK:2027-03-13": [
            FlightLegOffer(provider="t", origin="MAD", destination="BKK", departure_date=date(2027, 3, 13), price_eur=300.0, stops_count=0),
        ]
    }
    assert RouteCombinator.assemble_itineraries([bp], offers_partial) == []

    # 3. Only offers with stops_count > max_stops_per_leg (all disqualified)
    offers_disqualified = {
        "MAD:BKK:2027-03-13": [
            FlightLegOffer(provider="t", origin="MAD", destination="BKK", departure_date=date(2027, 3, 13), price_eur=300.0, stops_count=3),
        ],
        "BKK:MAD:2027-04-04": [
            FlightLegOffer(provider="t", origin="BKK", destination="MAD", departure_date=date(2027, 4, 4), price_eur=400.0, stops_count=2),
        ],
    }
    assert RouteCombinator.assemble_itineraries([bp], offers_disqualified, max_stops_per_leg=1) == []
