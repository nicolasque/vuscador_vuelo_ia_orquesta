"""RapidAPI Flight Provider (flights-sky / Skyscanner connector)."""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional
import requests

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)

# Pre-cached popular entities to avoid initial auto-complete roundtrips
COMMON_ENTITIES: Dict[str, str] = {
    "MAD": "eyJlIjoiOTU1NjUwNzciLCJzIjoiTUFEIiwiaCI6IjI3NTQ0ODUwIiwidCI6IkFJUlBPUlQifQ==",
    "BCN": "eyJlIjoiOTU1NjUwODUiLCJzIjoiQkNOIiwiaCI6IjI3NTQ4MjgzIiwidCI6IkFJUlBPUlQifQ==",
    "TYO": "eyJlIjoiMjc1NDIwODkiLCJzIjoiVFlPQSIsImgiOiIyNzU0MjA4OSIsInQiOiJDSVRZIn0=",
    "NRT": "eyJlIjoiMjc1NDIwODkiLCJzIjoiVFlPQSIsImgiOiIyNzU0MjA4OSIsInQiOiJDSVRZIn0=",
    "HND": "eyJlIjoiMjc1NDIwODkiLCJzIjoiVFlPQSIsImgiOiIyNzU0MjA4OSIsInQiOiJDSVRZIn0=",
    "OSA": "eyJlIjoiMjc1NDI5MDgiLCJzIjoiT1NBQSIsImgiOiIyNzU0MjkwOCIsInQiOiJDSVRZIn0=",
    "KIX": "eyJlIjoiMjc1NDI5MDgiLCJzIjoiT1NBQSIsImgiOiIyNzU0MjkwOCIsInQiOiJDSVRZIn0=",
    "IST": "eyJlIjoiMjc1NDI5MDMiLCJzIjoiSVNUQSIsImgiOiIyNzU0MjkwMyIsInQiOiJDSVRZIn0=",
    "DOH": "eyJlIjoiOTU2NzM4NTIiLCJzIjoiRE9IIiwiaCI6IjI3NTQwNzg1IiwidCI6IkFJUlBPUlQifQ==",
    "DXB": "eyJlIjoiMjc1NDA4MzkiLCJzIjoiRFhCQSIsImgiOiIyNzU0MDgzOSIsInQiOiJDSVRZIn0=",
    "LON": "eyJlIjoiMjc1NDQwMDgiLCJzIjoiTE9ORCIsImgiOiIyNzU0NDAwOCIsInQiOiJDSVRZIn0=",
    "LHR": "eyJlIjoiMjc1NDQwMDgiLCJzIjoiTE9ORCIsImgiOiIyNzU0NDAwOCIsInQiOiJDSVRZIn0=",
    "PAR": "eyJlIjoiMjc1Mzk3MzMiLCJzIjoiUEFSSSIsImgiOiIyNzUzOTczMyIsInQiOiJDSVRZIn0=",
    "CDG": "eyJlIjoiMjc1Mzk3MzMiLCJzIjoiUEFSSSIsImgiOiIyNzUzOTczMyIsInQiOiJDSVRZIn0=",
    "ROM": "eyJlIjoiMjc1Mzk3OTMiLCJzIjoiUk9NRSIsImgiOiIyNzUzOTc5MyIsInQiOiJDSVRZIn0=",
    "FCO": "eyJlIjoiMjc1Mzk3OTMiLCJzIjoiUk9NRSIsImgiOiIyNzUzOTc5MyIsInQiOiJDSVRZIn0=",
    "BKK": "eyJlIjoiMjc1MzY2NzEiLCJzIjoiQktLVCIsImgiOiIyNzUzNjY3MSIsInQiOiJDSVRZIn0=",
    "SIN": "eyJlIjoiMjc1NDYxMTEiLCJzIjoiU0lOUyIsImgiOiIyNzU0NjExMSIsInQiOiJDSVRZIn0=",
}

IATA_FALLBACK_NAMES: Dict[str, str] = {
    "PAR": "Paris",
    "ROM": "Rome",
    "LON": "London",
    "NYC": "New York",
    "DXB": "Dubai",
    "MIL": "Milan",
    "BKK": "Bangkok",
    "SIN": "Singapore",
    "KUL": "Kuala Lumpur",
    "SEL": "Seoul",
    "ICN": "Incheon",
    "BOG": "Bogota",
    "EZE": "Buenos Aires",
    "GRU": "Sao Paulo",
    "MEX": "Mexico City",
    "SCL": "Santiago",
    "LIM": "Lima",
    "MUC": "Munich",
    "FRA": "Frankfurt",
    "AMS": "Amsterdam",
    "VIE": "Vienna",
    "ZRH": "Zurich",
}


class RapidApiFlightProvider(BaseFlightProvider):
    """Provider connecting to Sky Scrapper / Skyscanner search on RapidAPI."""

    def __init__(self, api_key: str, api_host: str = "flights-sky.p.rapidapi.com"):
        self.api_key = api_key
        self.api_host = api_host
        self._entity_cache: Dict[str, str] = dict(COMMON_ENTITIES)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=30, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @property
    def name(self) -> str:
        return f"RapidAPI ({self.api_host})"

    def _get_entity_id(self, code: str) -> Optional[str]:
        """Resolves an IATA or city code to a Skyscanner entity ID for flights-sky."""
        code_upper = code.strip().upper()
        if code_upper in self._entity_cache:
            return self._entity_cache[code_upper]

        # Try auto-complete lookup by code first, then fallback name
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.api_host,
        }
        queries = [code_upper]
        if code_upper in IATA_FALLBACK_NAMES:
            queries.append(IATA_FALLBACK_NAMES[code_upper])

        for q in queries:
            try:
                resp = self.session.get(
                    f"https://{self.api_host}/flights/auto-complete",
                    headers=headers,
                    params={"query": q},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        pres_id = data[0].get("presentation", {}).get("id")
                        if pres_id:
                            self._entity_cache[code_upper] = pres_id
                            logger.info(f"Resolved RapidAPI entity for {code_upper}: {pres_id[:20]}...")
                            return pres_id
            except Exception as e:
                logger.warning(f"Error querying RapidAPI auto-complete for '{q}': {e}")

        logger.error(f"Could not resolve RapidAPI entity ID for airport code: {code_upper}")
        return None

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
        }

        # Check if using flights-sky.p.rapidapi.com
        if "flights-sky" in self.api_host:
            from_entity = self._get_entity_id(origin)
            to_entity = self._get_entity_id(destination)
            if not from_entity or not to_entity:
                logger.warning(f"Skipping search ({origin}->{destination}): entity ID could not be resolved.")
                return []

            params = {
                "fromEntityId": from_entity,
                "toEntityId": to_entity,
                "departDate": travel_date.isoformat(),
                "currency": "EUR",
            }
            url = f"https://{self.api_host}/flights/search-one-way"
        else:
            # Fallback legacy sky-scrapper structure
            params = {
                "originSkyId": origin.upper(),
                "destinationSkyId": destination.upper(),
                "date": travel_date.isoformat(),
                "adults": str(adults),
                "currency": "EUR",
            }
            url = f"https://{self.api_host}/api/v1/flights/searchFlights"

        try:
            resp = self.session.get(url, headers=headers, params=params, timeout=20)
            if resp.status_code == 429:
                detail = "Rate limit or quota exceeded"
                try:
                    detail = resp.json().get("message", detail)
                except Exception:
                    pass
                raise RuntimeError(f"RapidAPI (HTTP 429): {detail}")
            resp.raise_for_status()
            data = resp.json()
            return self._parse_rapidapi_offers(data, origin, destination, travel_date)
        except Exception as e:
            logger.error(f"RapidAPI flight search error ({origin}->{destination} on {travel_date}): {e}")
            raise

    def _parse_rapidapi_offers(
        self, data: dict, origin: str, destination: str, travel_date: date
    ) -> List[FlightLegOffer]:
        offers: List[FlightLegOffer] = []
        itins = data.get("data", {}).get("itineraries", [])

        for it in itins:
            try:
                price_obj = it.get("price", {})
                price_eur = float(price_obj.get("raw", 0.0))
                if price_eur <= 0:
                    continue

                legs = it.get("legs", [])
                if not legs:
                    continue

                first_leg = legs[0]
                dur_mins = first_leg.get("durationInMinutes", 120)
                stop_count = first_leg.get("stopCount", 0)
                carrier_items = first_leg.get("carriers", {}).get("marketing", [])
                carrier_names = [c.get("name", "Airline") for c in carrier_items if c.get("name")]
                carrier_code = carrier_items[0].get("alternateId", "XX") if carrier_items else "XX"

                # Parse detailed segments if available
                segments: List[FlightSegment] = []
                raw_segments = first_leg.get("segments", [])

                if raw_segments:
                    for s in raw_segments:
                        m_carrier = s.get("marketingCarrier", {})
                        s_code = m_carrier.get("alternateId") or m_carrier.get("displayCode") or carrier_code
                        s_name = m_carrier.get("name") or (carrier_names[0] if carrier_names else "Airline")
                        s_num = f"{s_code}{s.get('flightNumber', '')}"
                        s_dep_str = s.get("departure", f"{travel_date.isoformat()}T10:00:00")
                        s_arr_str = s.get("arrival", f"{travel_date.isoformat()}T14:00:00")
                        s_dur = s.get("durationInMinutes", 60)
                        s_orig = s.get("origin", {}).get("displayCode") or origin
                        s_dest = s.get("destination", {}).get("displayCode") or destination

                        dep_dt = datetime.fromisoformat(s_dep_str.replace("Z", ""))
                        arr_dt = datetime.fromisoformat(s_arr_str.replace("Z", ""))

                        segments.append(
                            FlightSegment(
                                carrier_code=s_code,
                                carrier_name=s_name,
                                flight_number=s_num,
                                departure_airport=s_orig,
                                arrival_airport=s_dest,
                                departure_time=dep_dt,
                                arrival_time=arr_dt,
                                duration_minutes=s_dur,
                            )
                        )
                else:
                    dep_time_str = first_leg.get("departure", f"{travel_date.isoformat()}T10:00:00")
                    arr_time_str = first_leg.get("arrival", f"{travel_date.isoformat()}T14:00:00")
                    dep_dt = datetime.fromisoformat(dep_time_str.replace("Z", ""))
                    arr_dt = datetime.fromisoformat(arr_time_str.replace("Z", ""))

                    segments.append(
                        FlightSegment(
                            carrier_code=carrier_code,
                            carrier_name=carrier_names[0] if carrier_names else "Airline",
                            flight_number=f"{carrier_code}{first_leg.get('id', '100')[:4]}",
                            departure_airport=origin,
                            arrival_airport=destination,
                            departure_time=dep_dt,
                            arrival_time=arr_dt,
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
                        stops_count=stop_count,
                        airline_names=carrier_names if carrier_names else ["Airline"],
                        booking_url=booking_url,
                        cabin_class="ECONOMY",
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Error parsing RapidAPI itinerary: {parse_err}")
                continue

        offers.sort(key=lambda o: o.price_eur)
        return offers
