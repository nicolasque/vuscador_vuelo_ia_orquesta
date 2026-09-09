"""Tests for RapidApiFlightProvider."""

from datetime import date
from unittest.mock import MagicMock, patch
from vusca.providers.rapidapi import RapidApiFlightProvider


def test_rapidapi_provider_parse():
    provider = RapidApiFlightProvider(api_key="dummy_key", api_host="flights-sky.p.rapidapi.com")
    
    mock_response_data = {
        "status": True,
        "data": {
            "itineraries": [
                {
                    "id": "itin_1",
                    "price": {"raw": 450.50, "formatted": "450 €"},
                    "legs": [
                        {
                            "id": "leg_1",
                            "durationInMinutes": 900,
                            "stopCount": 1,
                            "departure": "2026-10-15T10:00:00",
                            "arrival": "2026-10-16T08:00:00",
                            "carriers": {
                                "marketing": [{"alternateId": "TK", "name": "Turkish Airlines"}]
                            },
                            "segments": [
                                {
                                    "origin": {"displayCode": "MAD"},
                                    "destination": {"displayCode": "IST"},
                                    "departure": "2026-10-15T10:00:00",
                                    "arrival": "2026-10-15T15:00:00",
                                    "durationInMinutes": 240,
                                    "flightNumber": "1858",
                                    "marketingCarrier": {"alternateId": "TK", "name": "Turkish Airlines"},
                                },
                                {
                                    "origin": {"displayCode": "IST"},
                                    "destination": {"displayCode": "TYO"},
                                    "departure": "2026-10-15T18:00:00",
                                    "arrival": "2026-10-16T08:00:00",
                                    "durationInMinutes": 660,
                                    "flightNumber": "198",
                                    "marketingCarrier": {"alternateId": "TK", "name": "Turkish Airlines"},
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_get.return_value = mock_resp

        offers = provider.search_leg("MAD", "TYO", date(2026, 10, 15))

        assert len(offers) == 1
        offer = offers[0]
        assert offer.price_eur == 450.50
        assert offer.stops_count == 1
        assert len(offer.segments) == 2
        assert offer.segments[0].carrier_code == "TK"
        assert offer.segments[0].flight_number == "TK1858"
        assert offer.segments[1].departure_airport == "IST"
