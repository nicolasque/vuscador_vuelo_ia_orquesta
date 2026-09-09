"""Tests for GoogleFlightsProvider."""

from datetime import date
from unittest.mock import MagicMock, patch
from vusca.providers.google_flights import GoogleFlightsProvider, _parse_google_flight_time


def test_parse_google_flight_time():
    fallback = date(2026, 11, 8)
    dt1 = _parse_google_flight_time("2026-11-8 12:45", fallback)
    assert dt1.year == 2026
    assert dt1.month == 11
    assert dt1.day == 8
    assert dt1.hour == 12
    assert dt1.minute == 45

    dt2 = _parse_google_flight_time("08-11-2026 12:45 PM", fallback)
    assert dt2.hour == 12
    assert dt2.minute == 45


def test_google_flights_provider_parse():
    provider = GoogleFlightsProvider(api_key="dummy_key", api_host="google-flights2.p.rapidapi.com")

    mock_response = {
        "status": True,
        "data": {
            "itineraries": {
                "topFlights": [
                    {
                        "departure_time": "08-11-2026 12:45 PM",
                        "arrival_time": "08-11-2026 09:14 PM",
                        "duration": {"raw": 329, "text": "5 hr 29 min"},
                        "price": 188.0,
                        "stops": 1,
                        "flights": [
                            {
                                "departure_airport": {"airport_code": "MAD", "time": "2026-11-8 12:45"},
                                "arrival_airport": {"airport_code": "IST", "time": "2026-11-8 17:30"},
                                "airline": "Turkish Airlines",
                                "flight_number": "TK 1858",
                                "duration": {"raw": 285},
                            },
                            {
                                "departure_airport": {"airport_code": "IST", "time": "2026-11-8 20:00"},
                                "arrival_airport": {"airport_code": "NRT", "time": "2026-11-9 12:00"},
                                "airline": "Turkish Airlines",
                                "flight_number": "TK 198",
                                "duration": {"raw": 660},
                            },
                        ],
                    }
                ],
                "otherFlights": [],
            }
        },
    }

    with patch.object(provider.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response
        mock_get.return_value = mock_resp

        offers = provider.search_leg("MAD", "TYO", date(2026, 11, 8))

        assert len(offers) == 1
        offer = offers[0]
        assert offer.price_eur == 188.0
        assert offer.stops_count == 1
        assert len(offer.segments) == 2
        assert offer.segments[0].carrier_code == "TK"
        assert offer.segments[0].departure_airport == "MAD"
        assert offer.segments[1].arrival_airport == "NRT"
        assert "Turkish Airlines" in offer.airline_names
