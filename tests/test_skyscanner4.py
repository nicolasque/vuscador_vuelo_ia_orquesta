"""Tests for SkyscannerFlights4Provider."""

from datetime import date
from unittest.mock import MagicMock, patch
from vusca.providers.skyscanner4 import SkyscannerFlights4Provider


def test_skyscanner4_parse_offers():
    provider = SkyscannerFlights4Provider(api_key="test_key")

    mock_resp_data = {
        "success": True,
        "trip_type": "one-way",
        "results_count": 1,
        "currency": "EUR",
        "results": [
            {
                "id": "test_offer_123",
                "price_raw": 420.50,
                "price": "421 €",
                "carriers": ["Turkish Airlines"],
                "score": 0.95,
                "legs": [
                    {
                        "from": "MAD",
                        "to": "IST",
                        "dep": "2026-11-10T12:00:00",
                        "arr": "2026-11-10T17:30:00",
                        "dur_min": 330,
                        "stops": 0,
                        "segments": [
                            {
                                "flight": "TK1858",
                                "from": "MAD",
                                "to": "IST",
                                "dep": "2026-11-10T12:00:00",
                                "arr": "2026-11-10T17:30:00",
                                "dur_min": 330,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    offers = provider._parse_offers(
        mock_resp_data, origin="MAD", destination="IST", travel_date=date(2026, 11, 10)
    )

    assert len(offers) == 1
    o = offers[0]
    assert o.provider == "Skyscanner4"
    assert o.origin == "MAD"
    assert o.destination == "IST"
    assert o.price_eur == 420.50
    assert "Turkish Airlines" in o.airline_names
    assert o.total_duration_minutes == 330
    assert o.stops_count == 0
    assert len(o.segments) == 1
    assert o.segments[0].flight_number == "TK1858"


def test_skyscanner4_key_rotation_on_429():
    provider = SkyscannerFlights4Provider(api_key="key1,key2")
    assert len(provider.api_keys) == 2
    assert provider.api_key == "key1"

    provider.rotate_key()
    assert provider.api_key == "key2"
    provider.rotate_key()
    assert provider.api_key == "key1"
