"""Skyscanner Flights 4 API Provider via RapidAPI (skyscanner-flights4.p.rapidapi.com)."""

import logging
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Union
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class SkyscannerFlights4Provider(BaseFlightProvider):
    """Provider connecting to Skyscanner Flights 4 via RapidAPI (100 free requests/month)."""

    def __init__(
        self,
        api_key: Union[str, List[str]],
        api_host: str = "skyscanner-flights4.p.rapidapi.com",
    ):
        if isinstance(api_key, list):
            self.api_keys = [k.strip() for k in api_key if k.strip()]
        else:
            self.api_keys = [k.strip() for k in api_key.split(",") if k.strip()]
        self.current_key_idx = 0
        self.api_host = api_host
        self.base_url = f"https://{self.api_host}/api/v1/search"

    @property
    def api_key(self) -> str:
        if not self.api_keys:
            return ""
        return self.api_keys[self.current_key_idx]

    def rotate_key(self) -> str:
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            logger.info(f"Skyscanner4: Rotated to API key #{self.current_key_idx + 1}/{len(self.api_keys)}")
        return self.api_key

    @property
    def name(self) -> str:
        return "Skyscanner4"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        params = {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "date": travel_date.isoformat(),
            "adults": str(adults),
            "currency": "EUR",
            "cabin": "economy",
            "limit": "15",
            "offset": "0",
        }

        max_attempts = max(1, len(self.api_keys))
        last_exception = None

        for attempt in range(max_attempts):
            current_key = self.api_key
            headers = {
                "x-rapidapi-key": current_key,
                "x-rapidapi-host": self.api_host,
                "Content-Type": "application/json",
            }

            try:
                resp = requests.get(self.base_url, headers=headers, params=params, timeout=25)
                if resp.status_code == 429:
                    detail = "Skyscanner4 Rate limit or quota exceeded"
                    try:
                        detail = resp.json().get("message", detail)
                    except Exception:
                        pass

                    if len(self.api_keys) > 1 and attempt < max_attempts - 1:
                        logger.warning(f"Skyscanner4 key #{self.current_key_idx + 1} hit 429 ({detail}). Rotating...")
                        self.rotate_key()
                        continue
                    raise RuntimeError(f"Skyscanner4 (HTTP 429): {detail}")

                resp.raise_for_status()
                data = resp.json()
                return self._parse_offers(data, origin, destination, travel_date)
            except Exception as e:
                last_exception = e
                err_str = str(e).lower()
                if ("quota" in err_str or "rate limit" in err_str or "429" in err_str) and len(self.api_keys) > 1 and attempt < max_attempts - 1:
                    logger.warning(f"Skyscanner4 key error ({e}). Rotating...")
                    self.rotate_key()
                    continue
                logger.error(
                    f"Skyscanner4 search error ({origin}->{destination} on {travel_date}): {e}"
                )
                raise

        if last_exception:
            raise last_exception
        return []

    def _parse_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        results = data.get("results", [])

        for res in results:
            price_raw = res.get("price_raw")
            if price_raw is None:
                continue
            try:
                price_eur = float(price_raw)
            except (ValueError, TypeError):
                continue

            carriers = res.get("carriers", [])
            airline_name = carriers[0] if carriers else "Skyscanner"
            legs = res.get("legs", [])
            if not legs:
                continue

            # Take the primary leg
            leg_info = legs[0]
            dep_str = leg_info.get("dep")
            arr_str = leg_info.get("arr")

            try:
                dep_dt = datetime.fromisoformat(dep_str) if dep_str else datetime.combine(travel_date, datetime.min.time())
            except Exception:
                dep_dt = datetime.combine(travel_date, datetime.min.time())

            try:
                arr_dt = datetime.fromisoformat(arr_str) if arr_str else dep_dt
            except Exception:
                arr_dt = dep_dt

            dur_min = int(leg_info.get("dur_min", 0))
            stops_count = int(leg_info.get("stops", 0))

            # Parse segments
            segments: List[FlightSegment] = []
            for s in leg_info.get("segments", []):
                s_dep_str = s.get("dep")
                s_arr_str = s.get("arr")
                try:
                    s_dep = datetime.fromisoformat(s_dep_str) if s_dep_str else dep_dt
                except Exception:
                    s_dep = dep_dt
                try:
                    s_arr = datetime.fromisoformat(s_arr_str) if s_arr_str else arr_dt
                except Exception:
                    s_arr = arr_dt

                flight_code = s.get("flight", "")
                carrier_code = flight_code[:2] if len(flight_code) >= 2 else "XX"

                segments.append(
                    FlightSegment(
                        carrier_code=carrier_code,
                        carrier_name=airline_name,
                        flight_number=flight_code or f"{carrier_code}100",
                        departure_airport=s.get("from", origin),
                        arrival_airport=s.get("to", destination),
                        departure_time=s_dep,
                        arrival_time=s_arr,
                        duration_minutes=int(s.get("dur_min", 0)),
                    )
                )

            if segments and len(segments) > 1:
                stops_count = max(stops_count, len(segments) - 1)

            if not segments:
                segments.append(
                    FlightSegment(
                        carrier_code=airline_name[:2].upper() if len(airline_name) >= 2 else "XX",
                        carrier_name=airline_name,
                        flight_number=f"{airline_name[:2].upper()}101",
                        departure_airport=origin.upper(),
                        arrival_airport=destination.upper(),
                        departure_time=dep_dt,
                        arrival_time=arr_dt,
                        duration_minutes=dur_min,
                    )
                )

            booking_url = f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}+on+{travel_date.isoformat()}"

            offer = FlightLegOffer(
                provider=self.name,
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=travel_date,
                price_eur=price_eur,
                segments=segments,
                total_duration_minutes=dur_min,
                stops_count=stops_count,
                airline_names=[airline_name] if airline_name else ["Skyscanner"],
                booking_url=booking_url,
                cabin_class="ECONOMY",
            )
            offers.append(offer)

        offers.sort(key=lambda o: o.price_eur)
        return offers
