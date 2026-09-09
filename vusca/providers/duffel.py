"""Duffel Flights API provider."""

import logging
from datetime import date, datetime
from typing import List
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class DuffelProvider(BaseFlightProvider):
    """Provider connecting to Duffel Flights API (supports free test tokens)."""

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.duffel.com/air/offer_requests"

    @property
    def name(self) -> str:
        return "Duffel"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "data": {
                "slices": [
                    {
                        "origin": origin.upper(),
                        "destination": destination.upper(),
                        "departure_date": travel_date.isoformat(),
                    }
                ],
                "passengers": [{"type": "adult"} for _ in range(adults)],
                "cabin_class": "economy",
                "return_offers": True,
            }
        }

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 429:
                raise RuntimeError("Duffel rate limit exceeded (HTTP 429)")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_duffel_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.error(f"Duffel search error ({origin}->{destination} on {travel_date}): {e}")
            raise

    def _parse_duffel_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        raw_offers = data.get("data", {}).get("offers", [])

        for offer in raw_offers:
            try:
                total_amount = float(offer.get("total_amount", 0.0))
                slices = offer.get("slices", [])
                if not slices:
                    continue

                slice_item = slices[0]
                dur_str = slice_item.get("duration", "PT3H")
                # Parse duration e.g. PT4H30M
                dur_mins = self._parse_iso_duration(dur_str)

                segments = slice_item.get("segments", [])
                parsed_segments: List[FlightSegment] = []
                carrier_names: List[str] = []

                for seg in segments:
                    carrier = seg.get("operating_carrier", {})
                    c_name = carrier.get("name", "Airline")
                    c_code = carrier.get("iata_code", "XX")
                    if c_name not in carrier_names:
                        carrier_names.append(c_name)

                    dep_dt = datetime.fromisoformat(seg["departing_at"].replace("Z", ""))
                    arr_dt = datetime.fromisoformat(seg["arriving_at"].replace("Z", ""))
                    seg_mins = int((arr_dt - dep_dt).total_seconds() / 60)

                    parsed_segments.append(
                        FlightSegment(
                            carrier_code=c_code,
                            carrier_name=c_name,
                            flight_number=f"{c_code}{seg.get('operating_carrier_flight_number', '100')}",
                            departure_airport=seg.get("origin", {}).get("iata_code", origin),
                            arrival_airport=seg.get("destination", {}).get("iata_code", destination),
                            departure_time=dep_dt,
                            arrival_time=arr_dt,
                            duration_minutes=seg_mins,
                        )
                    )

                offers.append(
                    FlightLegOffer(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=travel_date,
                        price_eur=total_amount,
                        segments=parsed_segments,
                        total_duration_minutes=dur_mins,
                        stops_count=max(len(parsed_segments) - 1, 0),
                        airline_names=carrier_names,
                        booking_url=f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}+on+{travel_date.isoformat()}",
                        cabin_class="ECONOMY",
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Error parsing Duffel offer: {parse_err}")
                continue

        offers.sort(key=lambda o: o.price_eur)
        return offers

    def _parse_iso_duration(self, dur_str: str) -> int:
        import re
        hours = 0
        minutes = 0
        h = re.search(r"(\d+)H", dur_str)
        m = re.search(r"(\d+)M", dur_str)
        if h:
            hours = int(h.group(1))
        if m:
            minutes = int(m.group(1))
        return hours * 60 + minutes
