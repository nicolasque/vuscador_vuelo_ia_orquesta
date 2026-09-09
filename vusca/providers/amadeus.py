"""Amadeus Self-Service Flight Offers API provider."""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class AmadeusProvider(BaseFlightProvider):
    """Amadeus Self-Service flight provider supporting test & production environments."""

    def __init__(self, client_id: str, client_secret: str, environment: str = "test"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.environment = environment.lower()
        self.base_url = (
            "https://test.api.amadeus.com"
            if self.environment == "test"
            else "https://api.amadeus.com"
        )
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @property
    def name(self) -> str:
        return f"Amadeus ({self.environment})"

    def _ensure_access_token(self) -> str:
        now = datetime.utcnow()
        if self._access_token and self._token_expiry and now < self._token_expiry:
            return self._access_token

        token_url = f"{self.base_url}/v1/security/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            resp = requests.post(token_url, data=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("access_token")
            expires_in = data.get("expires_in", 1799)
            self._token_expiry = now + timedelta(seconds=expires_in - 60)
            return self._access_token
        except Exception as e:
            logger.error(f"Error obtaining Amadeus token: {e}")
            raise

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        token = self._ensure_access_token()
        offers_url = f"{self.base_url}/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": travel_date.isoformat(),
            "adults": adults,
            "currencyCode": "EUR",
            "max": 5,
        }

        try:
            resp = requests.get(offers_url, headers=headers, params=params, timeout=15)
            if resp.status_code == 429:
                logger.warning("Amadeus rate limit reached (HTTP 429)")
                raise RuntimeError("Rate limit exceeded")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_flight_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.error(f"Amadeus search error ({origin}->{destination} on {travel_date}): {e}")
            raise

    def _parse_flight_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        results: List[FlightLegOffer] = []
        raw_offers = data.get("data", [])
        carriers_dict = data.get("dictionaries", {}).get("carriers", {})

        for item in raw_offers:
            try:
                price_eur = float(item["price"]["total"])
                itineraries = item.get("itineraries", [])
                if not itineraries:
                    continue

                first_itinerary = itineraries[0]
                total_duration_str = first_itinerary.get("duration", "PT2H")
                # Parse PT2H30M format
                total_duration_mins = self._parse_iso_duration(total_duration_str)
                segments_data = first_itinerary.get("segments", [])

                parsed_segments: List[FlightSegment] = []
                airline_names = []

                for seg in segments_data:
                    carrier = seg.get("carrierCode", "XX")
                    carrier_name = carriers_dict.get(carrier, carrier)
                    if carrier_name not in airline_names:
                        airline_names.append(carrier_name)

                    dep_time = datetime.fromisoformat(seg["departure"]["at"])
                    arr_time = datetime.fromisoformat(seg["arrival"]["at"])
                    seg_dur_mins = self._parse_iso_duration(seg.get("duration", "PT1H"))

                    parsed_segments.append(
                        FlightSegment(
                            carrier_code=carrier,
                            carrier_name=carrier_name,
                            flight_number=f"{carrier}{seg.get('number', '')}",
                            departure_airport=seg["departure"]["iataCode"],
                            arrival_airport=seg["arrival"]["iataCode"],
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            duration_minutes=seg_dur_mins,
                        )
                    )

                results.append(
                    FlightLegOffer(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=travel_date,
                        price_eur=price_eur,
                        segments=parsed_segments,
                        total_duration_minutes=total_duration_mins,
                        stops_count=max(len(parsed_segments) - 1, 0),
                        airline_names=airline_names,
                        booking_url=f"https://www.google.com/travel/flights?q=one-way+flights+from+{origin}+to+{destination}+on+{travel_date.isoformat()}",
                        cabin_class="ECONOMY",
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Error parsing single Amadeus offer: {parse_err}")
                continue

        results.sort(key=lambda o: o.price_eur)
        return results

    def _parse_iso_duration(self, dur_str: str) -> int:
        """Parses ISO-8601 duration (e.g. PT4H35M) to minutes."""
        import re
        hours = 0
        minutes = 0
        h_match = re.search(r"(\d+)H", dur_str)
        m_match = re.search(r"(\d+)M", dur_str)
        if h_match:
            hours = int(h_match.group(1))
        if m_match:
            minutes = int(m_match.group(1))
        return hours * 60 + minutes
