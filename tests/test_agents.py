"""Unit tests for PTOAgent, RouteAgent, and SynthesisAgent."""

import pytest
from datetime import date, datetime
from vusca.agents.pto_agent import PTOAgent
from vusca.agents.route_agent import RouteAgent
from vusca.agents.synthesis_agent import SynthesisAgent
from vusca.models.calendar import PTOWindow
from vusca.models.flight import Itinerary, FlightLegOffer, FlightSegment, StopoverDetail


def test_pto_agent_strategy_rationale():
    agent = PTOAgent(country="ES", subdivision="MD")
    windows = agent.select_best_windows(
        start_search=date(2026, 10, 1),
        end_search=date(2026, 10, 31),
        max_pto_days=5,
        min_total_days=5,
        max_total_days=16,
    )
    assert len(windows) > 0
    rationale = agent.get_strategy_rationale(windows)
    assert "Objetivo Calendario" in rationale
    assert "Rendimiento Máximo" in rationale
    assert "Por qué se alimenta al motor" in rationale


def test_route_agent_hub_and_open_jaw_strategies():
    agent = RouteAgent()
    codes, names, reasons = agent.recommend_stopovers("MAD", "TYO", top_k=3)
    assert len(codes) >= 1

    hub_explanation = agent.get_hub_strategy_explanation(["IST", "DOH", "SDQ"])
    assert "Estambul" in hub_explanation
    assert "Doha" in hub_explanation
    assert "Santo Domingo" in hub_explanation

    # Test open-jaw explanations
    oj_japan = agent.get_open_jaw_strategy(["TYO"], ["OSA"])
    assert "Shinkansen" in oj_japan
    assert "Tokio" in oj_japan

    oj_colombia = agent.get_open_jaw_strategy(["BOG"], ["CTG", "MDE"])
    assert "Colombia" in oj_colombia
    assert "Cartagena" in oj_colombia

    oj_bkk = agent.get_open_jaw_strategy(["BKK"], ["HKT"])
    assert "playa" in oj_bkk or "islas" in oj_bkk


def test_synthesis_agent_multi_origin_report_with_links():
    agent = SynthesisAgent()

    leg1 = FlightLegOffer(
        provider="GoogleFlights",
        origin="MAD",
        destination="SDQ",
        departure_date=date(2026, 10, 24),
        price_eur=350.0,
        airline_names=["Air Europa"],
        segments=[
            FlightSegment(
                carrier_code="UX",
                carrier_name="Air Europa",
                flight_number="UX 89",
                departure_airport="MAD",
                arrival_airport="SDQ",
                departure_time=datetime(2026, 10, 24, 15, 0),
                arrival_time=datetime(2026, 10, 24, 19, 0),
                duration_minutes=540,
            )
        ],
    )
    leg2 = FlightLegOffer(
        provider="GoogleFlights",
        origin="SDQ",
        destination="BOG",
        departure_date=date(2026, 10, 26),
        price_eur=100.0,
        airline_names=["Arajet"],
        segments=[],
    )
    leg3 = FlightLegOffer(
        provider="GoogleFlights",
        origin="BOG",
        destination="MAD",
        departure_date=date(2026, 11, 8),
        price_eur=450.0,
        airline_names=["Air Europa"],
        segments=[],
    )

    itin_mad = Itinerary(
        itinerary_id="itin-mad-1",
        origin="MAD",
        final_destination="BOG",
        start_date=date(2026, 10, 24),
        end_date=date(2026, 11, 8),
        legs=[leg1, leg2, leg3],
        stopovers=[
            StopoverDetail(
                city_code="SDQ",
                city_name="Santo Domingo",
                stay_days=2,
                arrival_date=date(2026, 10, 24),
                departure_date=date(2026, 10, 26),
            )
        ],
        route_summary="MAD ➔ Santo Domingo (2d) ➔ BOG ➔ MAD",
    )
    itin_mad.calculate_totals(work_days=9)

    # Bilbao itinerary
    leg_bio_1 = FlightLegOffer(
        provider="GoogleFlights",
        origin="BIO",
        destination="BOG",
        departure_date=date(2026, 10, 24),
        price_eur=560.0,
        airline_names=["Iberia"],
        segments=[],
    )
    leg_bio_2 = FlightLegOffer(
        provider="GoogleFlights",
        origin="BOG",
        destination="BIO",
        departure_date=date(2026, 11, 8),
        price_eur=460.0,
        airline_names=["Air Europa"],
        segments=[],
    )
    itin_bio = Itinerary(
        itinerary_id="itin-bio-1",
        origin="BIO",
        final_destination="BOG",
        start_date=date(2026, 10, 24),
        end_date=date(2026, 11, 8),
        legs=[leg_bio_1, leg_bio_2],
        stopovers=[],
        route_summary="BIO ➔ BOG ➔ BIO",
    )
    itin_bio.calculate_totals(work_days=9)

    ranked = agent.evaluate_and_rank([itin_mad, itin_bio])
    assert len(ranked) == 2
    assert ranked[0].ai_score > 0

    search_context = {
        "origins": ["MAD", "BIO"],
        "destinations": ["BOG"],
        "return_destinations": ["BOG", "CTG"],
        "pto_strategy": "- **Estrategia:** Puente del 12 de Octubre.",
        "hub_strategy": "- **Hubs:** Santo Domingo para conectar con Arajet.",
        "open_jaw_strategy": "Recorrer Colombia de sur a norte.",
        "constraints": {"max_scales": 2, "max_stops_per_leg": 1},
        "stats": {"total_blueprints": 100, "total_leg_tasks": 20},
    }

    report = agent.generate_final_report(
        origin="MAD, BIO",
        destination="BOG",
        itineraries=ranked,
        candidate_stopover_names={"MAD": "Madrid", "BIO": "Bilbao", "BOG": "Bogotá", "SDQ": "Santo Domingo"},
        search_context=search_context,
    )

    # Check key sections and content
    assert "Configuración y Justificación de la Búsqueda" in report
    assert "Estrategia de Calendario y Festivos" in report
    assert "Estrategia de Hubs y Paradas Intermedias" in report
    assert "Las 4 Mejores Opciones desde Madrid (MAD)" in report
    assert "Las 4 Mejores Opciones desde Bilbao (BIO)" in report
    assert "https://www.google.com/travel/flights?q=one-way+flights+from+MAD+to+SDQ" in report
    assert "Shinkansen" not in report  # Verified: no hardcoded Japan text for Colombia


def test_synthesis_agent_with_deterministic_curator_on_large_query():
    """Verifies that for large itinerary datasets (>= activation_threshold),
    SynthesisAgent triggers DeterministicCurator and embeds exact market statistics
    and balanced diversity in the executive report.
    """
    from tests.test_curator import make_mock_itinerary
    import random
    random.seed(99)

    origins = ["MAD", "BIO"]
    destinations = ["TYO", "OSA", "FUK"]
    hubs = ["IST", "ICN", "SIN", "BKK", "HAN", "HKG"]

    large_itins = []
    for i in range(250):
        orig = random.choice(origins)
        ret_arr = random.choice(origins)
        dest = random.choice(destinations)
        hub = random.choice(hubs)
        price = round(random.uniform(900.0, 1800.0), 2)
        score = round(random.uniform(70.0, 95.0), 1)
        pto = round(random.uniform(1.8, 2.8), 2)
        large_itins.append(make_mock_itinerary(f"it_{i}", orig, dest, ret_arr, price, score, pto, hub))

    agent = SynthesisAgent()
    assert agent.curator.is_applicable(len(large_itins))

    report = agent.generate_final_report(
        origin="MAD, BIO",
        destination="TYO, OSA",
        itineraries=large_itins,
        candidate_stopover_names={"MAD": "Madrid", "BIO": "Bilbao", "TYO": "Tokio", "OSA": "Osaka", "IST": "Estambul"},
        search_context={
            "origins": ["MAD", "BIO"],
            "destinations": ["TYO", "OSA"],
            "pto_strategy": "Optimización Semana Santa",
        },
    )

    # Verify that deterministic market stats section was rendered
    assert "Análisis Determinista y Estadísticas de Mercado" in report
    assert "250 itinerarios reales" in report
    assert "Rango global de mercado:" in report
    assert "Precio mediano:" in report
    assert "Las 4 Mejores Opciones desde Madrid (MAD)" in report
    assert "Las 4 Mejores Opciones desde Bilbao (BIO)" in report


def test_synthesis_agent_with_allowed_scenarios():
    from tests.test_curator import make_mock_itinerary

    itins = [
        make_mock_itinerary("it_bio", "BIO", "TYO", "BIO", 1100.0, 85.0, 2.4, "IST"),
        make_mock_itinerary("it_mad", "MAD", "TYO", "MAD", 950.0, 90.0, 2.4, "IST"),
        make_mock_itinerary("it_mix", "MAD", "TYO", "BIO", 980.0, 88.0, 2.4, "IST"),
    ]

    agent = SynthesisAgent()
    report = agent.generate_final_report(
        origin="MAD, BIO",
        destination="TYO, OSA",
        itineraries=itins,
        candidate_stopover_names={"MAD": "Madrid", "BIO": "Bilbao", "TYO": "Tokio", "OSA": "Osaka", "IST": "Estambul"},
        search_context={
            "origins": ["MAD", "BIO"],
            "destinations": ["TYO", "OSA"],
            "allowed_scenarios": [("BIO", "BIO"), ("MAD", "MAD"), ("MAD", "BIO")],
            "pto_strategy": "Optimización Semana Santa",
        },
    )

    assert "BIO ➔ BIO" in report
    assert "MAD ➔ MAD" in report
    assert "MAD ➔ BIO" in report
    assert "Ruta Mixta" in report

