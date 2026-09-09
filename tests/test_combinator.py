"""Tests for RouteCombinator."""

from datetime import date
from vusca.models.calendar import PTOWindow
from vusca.core.combinator import RouteCombinator


def test_combinator_generates_blueprints_and_deduplicates():
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
        candidate_stopovers=["IST", "DOH"],
        stopover_names={"IST": "Estambul", "DOH": "Doha"},
        min_stopover_days=1,
        max_stopover_days=2,
    )

    blueprints, tasks = combinator.generate_blueprints()

    assert len(blueprints) > 0
    assert len(tasks) > 0

    # Ensure no duplicate tasks (origin, dest, date)
    task_keys = [f"{t.origin}:{t.destination}:{t.travel_date}" for t in tasks]
    assert len(task_keys) == len(set(task_keys))

    # Check direct route is included
    direct_bp = [b for b in blueprints if "direct" in b.blueprint_id]
    assert len(direct_bp) == 1


def test_combinator_with_open_jaw_returns():
    window = PTOWindow(
        start_date=date(2027, 3, 19),
        end_date=date(2027, 3, 28),
        total_days=10,
        work_days_needed=3,
        weekend_days=4,
        holiday_days=3,
        efficiency_ratio=3.33,
    )

    combinator = RouteCombinator(
        origin="MAD",
        destination="TYO",
        return_destinations=["TYO", "KIX"],
        candidate_windows=[window],
        candidate_stopovers=["IST"],
        stopover_names={"IST": "Estambul", "TYO": "Tokio", "KIX": "Osaka"},
        min_stopover_days=1,
        max_stopover_days=2,
    )

    blueprints, tasks = combinator.generate_blueprints()

    # Blueprints should include routes returning to MAD from TYO AND from KIX
    kix_returns = [b for b in blueprints if any(leg[0] == "KIX" for leg in b.leg_keys)]
    tyo_returns = [b for b in blueprints if any(leg[0] == "TYO" for leg in b.leg_keys)]

    assert len(kix_returns) > 0
    assert len(tyo_returns) > 0


def test_combinator_multi_origin_and_destinations():
    window = PTOWindow(
        start_date=date(2027, 3, 19),
        end_date=date(2027, 4, 11),
        total_days=24,
        work_days_needed=13,
        weekend_days=8,
        holiday_days=3,
        efficiency_ratio=1.85,
    )

    combinator = RouteCombinator(
        origins=["MAD", "BCN"],
        destinations=["TYO", "OSA"],
        return_destinations=["TYO", "OSA"],
        candidate_windows=[window],
        candidate_stopovers=["BKK", "SIN", "ICN"],
        stopover_names={"BKK": "Bangkok", "SIN": "Singapur", "ICN": "Seúl", "TYO": "Tokio", "OSA": "Osaka", "MAD": "Madrid", "BCN": "Barcelona"},
        min_stopover_days=1,
        max_stopover_days=2,
    )

    blueprints, tasks = combinator.generate_blueprints()

    # Verify both MAD and BCN origins are present
    mad_bps = [b for b in blueprints if b.origin == "MAD"]
    bcn_bps = [b for b in blueprints if b.origin == "BCN"]
    assert len(mad_bps) > 0
    assert len(bcn_bps) > 0

    # Verify both TYO and OSA destinations are present
    tyo_dest = [b for b in blueprints if b.destination == "TYO"]
    osa_dest = [b for b in blueprints if b.destination == "OSA"]
    assert len(tyo_dest) > 0
    assert len(osa_dest) > 0

    # Estimate volume and verify metrics
    stats = combinator.estimate_task_volume()
    assert stats["total_blueprints"] == len(blueprints)
    assert stats["total_leg_tasks"] == len(tasks)
    assert "MAD ➔ BKK" in stats["corridors"] or "MAD ➔ TYO" in stats["corridors"]
    assert stats["api_calls_needed"] <= stats["total_leg_tasks"]


def test_combinator_asymmetric_stopovers_and_dual_stopovers():
    window = PTOWindow(
        start_date=date(2027, 3, 6),
        end_date=date(2027, 3, 28),
        total_days=23,
        work_days_needed=12,
        weekend_days=8,
        holiday_days=3,
        efficiency_ratio=1.92,
    )

    combinator = RouteCombinator(
        origins=["MAD", "BIO"],
        destinations=["TYO", "OSA"],
        return_destinations=["TYO", "OSA"],
        candidate_windows=[window],
        outbound_stopovers=["DOH", "DXB"],
        return_stopovers=["BKK", "SIN", "IST", "DOH", "DXB"],
        stopover_names={
            "DOH": "Doha",
            "DXB": "Dubái",
            "BKK": "Bangkok",
            "SIN": "Singapur",
            "IST": "Estambul",
            "TYO": "Tokio",
            "OSA": "Osaka",
            "MAD": "Madrid",
            "BIO": "Bilbao",
        },
        min_stopover_days=2,
        max_stopover_days=3,
        include_dual_stopovers=True,
    )

    blueprints, tasks = combinator.generate_blueprints()

    assert len(blueprints) > 0
    assert len(tasks) > 0

    # Ensure outbound stopovers have DOH and DXB
    outbound_doh = [b for b in blueprints if any(s.city_code == "DOH" and "ida" in s.highlights.lower() for s in b.stopovers)]
    assert len(outbound_doh) > 0

    # Ensure return stopovers have BKK and IST
    return_bkk = [b for b in blueprints if any(s.city_code == "BKK" and "regreso" in s.highlights.lower() for s in b.stopovers)]
    assert len(return_bkk) > 0

    # Ensure dual stopover routes exist (2 stopovers: one outbound, one return)
    dual_bps = [b for b in blueprints if len(b.stopovers) == 2]
    assert len(dual_bps) > 0
    assert any(b.stopovers[0].city_code == "DOH" and b.stopovers[1].city_code == "BKK" for b in dual_bps)


def test_assemble_itineraries_max_stops_per_leg_and_direction():
    from vusca.models.flight import FlightLegOffer

    window = PTOWindow(
        start_date=date(2027, 3, 6),
        end_date=date(2027, 3, 28),
        total_days=23,
        work_days_needed=12,
        weekend_days=8,
        holiday_days=3,
        efficiency_ratio=1.92,
    )

    combinator = RouteCombinator(
        origins=["MAD"],
        destinations=["TYO"],
        return_destinations=["TYO"],
        candidate_windows=[window],
        candidate_stopovers=["BKK"],
        min_stopover_days=2,
        max_stopover_days=2,
    )

    blueprints, _ = combinator.generate_blueprints()
    bp = [b for b in blueprints if b.has_outbound_stopover][0]

    # Offers with 2 stops should be filtered out by max_stops_per_leg=1
    offers_by_key = {
        f"MAD:BKK:{bp.start_date.isoformat()}": [
            FlightLegOffer(
                provider="test",
                origin="MAD",
                destination="BKK",
                departure_date=bp.start_date,
                price_eur=100.0,
                stops_count=2,  # 2 stops: should be ignored!
            ),
            FlightLegOffer(
                provider="test",
                origin="MAD",
                destination="BKK",
                departure_date=bp.start_date,
                price_eur=200.0,
                stops_count=1,  # 1 stop: valid
            ),
        ],
        f"BKK:TYO:{bp.leg_keys[1][2].isoformat()}": [
            FlightLegOffer(
                provider="test",
                origin="BKK",
                destination="TYO",
                departure_date=bp.leg_keys[1][2],
                price_eur=150.0,
                stops_count=0,  # 0 stops: valid
            ),
        ],
        f"TYO:MAD:{bp.end_date.isoformat()}": [
            FlightLegOffer(
                provider="test",
                origin="TYO",
                destination="MAD",
                departure_date=bp.end_date,
                price_eur=500.0,
                stops_count=0,
            ),
        ],
    }

    itins = RouteCombinator.assemble_itineraries(
        blueprints=[bp],
        offers_by_key=offers_by_key,
        max_scales_per_direction=2,
        max_stops_per_leg=1,
    )

    assert len(itins) == 1
    chosen_mad_bkk = [l for l in itins[0].legs if l.origin == "MAD" and l.destination == "BKK"][0]
    # Verify the 2-stop flight was rejected and the 1-stop was chosen
    assert chosen_mad_bkk.stops_count == 1
    assert chosen_mad_bkk.price_eur == 200.0


