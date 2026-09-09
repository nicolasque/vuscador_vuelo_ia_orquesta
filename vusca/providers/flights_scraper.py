"""Flights Scraper Data API Provider via RapidAPI (flights-scraper-data.p.rapidapi.com)."""

import logging
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Union
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class FlightsScraperDataProvider(BaseFlightProvider):
    """Provider connecting to Flights Scraper Data on RapidAPI."""

    def __init__(
        self,
        api_key: str,
        api_host: str = "flights-scraper-data.p.rapidapi.com",
    ):
        self.api_key = api_key
        self.api_host = api_host
        self.base_url = f"https://{self.api_host}/date-grid/for-oneway"

    @property
    def name(self) -> str:
        return "FlightsScraperData"

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
            "departureId": origin.upper(),
            "arrivalId": destination.upper(),
        }

        try:
            resp = requests.get(self.base_url, headers=headers, params=params, timeout=20)
            if resp.status_code == 429:
                raise RuntimeError("FlightsScraperData HTTP 429: Rate limit or quota exceeded")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("status") or not data.get("data"):
                logger.info(f"FlightsScraperData: No direct data for {origin}->{destination}: {data.get('message')}")
                return []
            return self._parse_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.warning(f"FlightsScraperData search failed ({origin}->{destination}): {e}")
            raise

    def _parse_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        raw_items = data.get("data") or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        for item in raw_items:
            price = float(item.get("price", 450.0))
            dep_dt = datetime.combine(travel_date, datetime.min.time())
            offer = FlightLegOffer(
                offer_id=str(uuid.uuid4())[:8],
                origin=origin.upper(),
                destination=destination.upper(),
                departure_time=dep_dt,
                arrival_time=dep_dt,
                price_eur=price,
                airline=item.get("airline", "ScraperAirline"),
                flight_number=f"{origin[:2]}101",
                duration_minutes=600,
                stops=1,
                provider_source=self.name,
                segments=[],
            )
            offers.append(offer)
        return offers
