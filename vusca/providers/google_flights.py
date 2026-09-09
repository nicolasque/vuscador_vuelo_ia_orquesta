"""Google Flights API Provider via RapidAPI (google-flights2.p.rapidapi.com)."""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Union
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)

# Common metropolitan codes that Google Flights requires as specific airport codes
METRO_TO_AIRPORT: Dict[str, str] = {
    "TYO": "NRT",
    "OSA": "KIX",
    "LON": "LHR",
    "PAR": "CDG",
    "ROM": "FCO",
    "NYC": "JFK",
    "BUE": "EZE",
    "SAO": "GRU",
    "SEL": "ICN",
    "MIL": "MXP",
    "WAS": "IAD",
    "CHI": "ORD",
    "MUC": "MUC",
    "FRA": "FRA",
}


def _parse_google_flight_time(time_str: str, default_date: date) -> datetime:
    """Parses Google Flights timestamp format (e.g. '2026-11-8 12:45' or '08-11-2026 12:45 PM')."""
    if not time_str:
        return datetime.combine(default_date, datetime.min.time())

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%d-%m-%Y %I:%M %p", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(time_str.strip(), fmt)
        except ValueError:
            pass

    try:
        parts = time_str.strip().split()
        if len(parts) == 2:
            d_parts = [int(p) for p in parts[0].split("-")]
            t_parts = [int(p) for p in parts[1].split(":")]
            return datetime(d_parts[0], d_parts[1], d_parts[2], t_parts[0], t_parts[1])
    except Exception:
        pass

    return datetime.combine(default_date, datetime.min.time())


class GoogleFlightsProvider(BaseFlightProvider):
    """Provider connecting to Google Flights via RapidAPI (google-flights2)."""

    def __init__(self, api_key: Union[str, List[str]], api_host: str = "google-flights2.p.rapidapi.com"):
        if isinstance(api_key, list):
            self.api_keys = [k.strip() for k in api_key if k.strip()]
        else:
            self.api_keys = [k.strip() for k in api_key.split(",") if k.strip()]
        self.current_key_idx = 0
        self.api_host = api_host
        self.base_url = f"https://{self.api_host}/api/v1/searchFlights"
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=30, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @property
    def api_key(self) -> str:
        if not self.api_keys:
            return ""
        return self.api_keys[self.current_key_idx]

    def rotate_key(self) -> str:
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            logger.info(f"Google Flights: Rotated to API key #{self.current_key_idx + 1}/{len(self.api_keys)}")
        return self.api_key

    @property
    def name(self) -> str:
        return "GoogleFlights"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        dep_code = METRO_TO_AIRPORT.get(origin.upper(), origin.upper())
        arr_code = METRO_TO_AIRPORT.get(destination.upper(), destination.upper())

        params = {
            "departure_id": dep_code,
            "arrival_id": arr_code,
            "outbound_date": travel_date.isoformat(),
            "travel_class": "ECONOMY",
            "adults": str(adults),
            "currency": "EUR",
            "language_code": "es",
            "country_code": "ES",
            "search_type": "best",
            "show_hidden": "1",
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
                resp = self.session.get(self.base_url, headers=headers, params=params, timeout=20)
                if resp.status_code == 429:
                    detail = "Google Flights Rate limit or quota exceeded"
                    try:
                        detail = resp.json().get("message", detail)
                    except Exception:
                        pass

                    if len(self.api_keys) > 1 and attempt < max_attempts - 1:
                        logger.warning(
                            f"Google Flights key #{self.current_key_idx + 1} hit 429/quota ({detail}). Rotating to next key..."
                        )
                        self.rotate_key()
                        continue
                    raise RuntimeError(f"GoogleFlights (HTTP 429): {detail}")

                resp.raise_for_status()
                data = resp.json()
                return self._parse_google_offers(data, origin, destination, travel_date)
            except Exception as e:
                last_exception = e
                # If error looks like quota exhausted, try next key if available
                err_str = str(e).lower()
                if ("quota" in err_str or "rate limit" in err_str or "429" in err_str) and len(self.api_keys) > 1 and attempt < max_attempts - 1:
                    logger.warning(f"Google Flights key error ({e}). Rotating to next key...")
                    self.rotate_key()
                    continue
                logger.error(
                    f"Google Flights search error ({origin}[{dep_code}]->{destination}[{arr_code}] on {travel_date}): {e}"
                )
                raise

        if last_exception:
            raise last_exception
        return []

    def _parse_google_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        itin_data = data.get("data", {}).get("itineraries", {})
        top_flights = itin_data.get("topFlights", [])
        other_flights = itin_data.get("otherFlights", [])

        all_flights = top_flights + other_flights

        for flight in all_flights:
            try:
                price = flight.get("price")
                if price is None:
                    continue
                price_eur = float(price)

                dur_mins = flight.get("duration", {}).get("raw", 120)
                raw_segments = flight.get("flights", [])
                stops = flight.get("stops")
                if stops is None or (raw_segments and len(raw_segments) > 1):
                    stops = max(int(stops or 0), len(raw_segments) - 1)
                else:
                    stops = int(stops or 0)

                segments: List[FlightSegment] = []
                airline_names: List[str] = []

                for s in raw_segments:
                    airline = s.get("airline", "Airline")
                    airline_names.append(airline)

                    flight_num_raw = s.get("flight_number", "XX100")
                    code_parts = flight_num_raw.split()
                    carrier_code = code_parts[0] if code_parts else "XX"

                    dep_info = s.get("departure_airport", {})
                    arr_info = s.get("arrival_airport", {})

                    seg_orig = dep_info.get("airport_code", origin)
                    seg_dest = arr_info.get("airport_code", destination)

                    dep_dt = _parse_google_flight_time(dep_info.get("time", ""), travel_date)
                    arr_dt = _parse_google_flight_time(arr_info.get("time", ""), travel_date)
                    seg_dur = s.get("duration", {}).get("raw", dur_mins)

                    segments.append(
                        FlightSegment(
                            carrier_code=carrier_code,
                            carrier_name=airline,
                            flight_number=flight_num_raw,
                            departure_airport=seg_orig,
                            arrival_airport=seg_dest,
                            departure_time=dep_dt,
                            arrival_time=arr_dt,
                            duration_minutes=seg_dur,
                        )
                    )

                if not segments:
                    # Synthesize basic segment if raw segments missing
                    segments.append(
                        FlightSegment(
                            carrier_code="XX",
                            carrier_name="Airline",
                            flight_number="XX100",
                            departure_airport=origin,
                            arrival_airport=destination,
                            departure_time=datetime.combine(travel_date, datetime.min.time()),
                            arrival_time=datetime.combine(travel_date, datetime.min.time()),
                            duration_minutes=dur_mins,
                        )
                    )

                booking_url = f"https://www.google.com/travel/flights?q=one-way+flights+from+{origin}+to+{destination}+on+{travel_date.isoformat()}"

                offers.append(
                    FlightLegOffer(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=travel_date,
                        price_eur=price_eur,
                        segments=segments,
                        total_duration_minutes=dur_mins,
                        stops_count=stops,
                        airline_names=list(set(airline_names)) if airline_names else ["Airline"],
                        booking_url=booking_url,
                        cabin_class="ECONOMY",
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Error parsing Google Flights itinerary: {parse_err}")
                continue

        offers.sort(key=lambda o: o.price_eur)
        return offers
