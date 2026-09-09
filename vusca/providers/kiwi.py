"""Kiwi / Tequila API provider for virtual interlining flight searches."""

import logging
from datetime import date, datetime
from typing import List
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class KiwiProvider(BaseFlightProvider):
    """Kiwi/Tequila API flight provider."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tequila.kiwi.com/v2/search"

    @property
    def name(self) -> str:
        return "Kiwi/Tequila"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        headers = {"apikey": self.api_key}
        date_str = travel_date.strftime("%d/%m/%Y")
        params = {
            "fly_from": origin.upper(),
            "fly_to": destination.upper(),
            "date_from": date_str,
            "date_to": date_str,
            "curr": "EUR",
            "adults": adults,
            "flight_type": "oneway",
            "limit": 5,
        }

        try:
            resp = requests.get(self.base_url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_kiwi_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.error(f"Kiwi search error ({origin}->{destination} on {travel_date}): {e}")
            raise

    def _parse_kiwi_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        results: List[FlightLegOffer] = []
        raw_items = data.get("data", [])

        for item in raw_items:
            try:
                price = float(item.get("price", 0.0))
                duration_secs = item.get("duration", {}).get("total", 0)
                duration_mins = int(duration_secs / 60)
                booking_url = item.get("deep_link")
                route_items = item.get("route", [])

                segments: List[FlightSegment] = []
                airline_names = []

                for r in route_items:
                    airline = r.get("airline", "XX")
                    if airline not in airline_names:
                        airline_names.append(airline)
                    dep_dt = datetime.fromisoformat(r["local_departure"].replace("Z", ""))
                    arr_dt = datetime.fromisoformat(r["local_arrival"].replace("Z", ""))
                    seg_mins = int((arr_dt - dep_dt).total_seconds() / 60)

                    segments.append(
                        FlightSegment(
                            carrier_code=airline,
                            carrier_name=airline,
                            flight_number=f"{airline}{r.get('flight_no', '')}",
                            departure_airport=r.get("flyFrom", ""),
                            arrival_airport=r.get("flyTo", ""),
                            departure_time=dep_dt,
                            arrival_time=arr_dt,
                            duration_minutes=seg_mins,
                        )
                    )

                results.append(
                    FlightLegOffer(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=travel_date,
                        price_eur=price,
                        segments=segments,
                        total_duration_minutes=duration_mins,
                        stops_count=max(len(segments) - 1, 0),
                        airline_names=airline_names,
                        booking_url=booking_url,
                        cabin_class="ECONOMY",
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Error parsing Kiwi offer: {parse_err}")
                continue

        results.sort(key=lambda o: o.price_eur)
        return results
