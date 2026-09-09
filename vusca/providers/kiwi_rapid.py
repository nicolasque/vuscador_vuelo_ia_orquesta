"""Kiwi Cheap Flights API Provider via RapidAPI (kiwi-com-cheap-flights.p.rapidapi.com)."""

import logging
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class KiwiRapidProvider(BaseFlightProvider):
    """Provider connecting to Kiwi Cheap Flights on RapidAPI."""

    def __init__(
        self,
        api_key: str,
        api_host: str = "kiwi-com-cheap-flights.p.rapidapi.com",
    ):
        self.api_key = api_key
        self.api_host = api_host
        self.base_url = f"https://{self.api_host}/round-trip"

    @property
    def name(self) -> str:
        return "KiwiRapid"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.api_host,
            "Content-Type": "application/json",
        }
        params = {
            "source": f"Airport:{origin.upper()}",
            "destination": f"Airport:{destination.upper()}",
            "currency": "eur",
            "adults": str(adults),
            "limit": "10",
        }

        try:
            resp = requests.get(self.base_url, headers=headers, params=params, timeout=20)
            if resp.status_code == 429:
                raise RuntimeError("KiwiRapid HTTP 429: Rate limit or quota exceeded")
            if resp.status_code == 402:
                raise RuntimeError("KiwiRapid HTTP 402: Upstream deployment disabled by provider")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.warning(f"KiwiRapid search failed ({origin}->{destination}): {e}")
            raise

    def _parse_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        for it in data.get("data", []):
            price = float(it.get("price", {}).get("amount", 500.0))
            dep_dt = datetime.combine(travel_date, datetime.min.time())
            offer = FlightLegOffer(
                offer_id=str(uuid.uuid4())[:8],
                origin=origin.upper(),
                destination=destination.upper(),
                departure_time=dep_dt,
                arrival_time=dep_dt,
                price_eur=price,
                airline=it.get("airline", "KiwiAirline"),
                flight_number=f"{origin[:2]}202",
                duration_minutes=600,
                stops=1,
                provider_source=self.name,
                segments=[],
            )
            offers.append(offer)
        return offers
