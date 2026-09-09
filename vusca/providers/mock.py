"""Realistic Mock Flight Provider for testing and offline execution."""

import hashlib
import math
from datetime import date, datetime, time, timedelta
from typing import List, Dict, Tuple

from vusca.models.flight import FlightLegOffer, FlightSegment
from vusca.providers.base import BaseFlightProvider


# Known airport approximate coordinates (lat, lon) and hubs
AIRPORT_COORDS: Dict[str, Tuple[float, float, str, str]] = {
    # Code: (lat, lon, City, Country)
    "MAD": (40.4839, -3.5679, "Madrid", "Spain"),
    "BCN": (41.2974, 2.0833, "Barcelona", "Spain"),
    "LIS": (38.7742, -9.1342, "Lisboa", "Portugal"),
    "CDG": (49.0097, 2.5479, "París", "France"),
    "ORY": (48.7262, 2.3652, "París Orly", "France"),
    "FCO": (41.8003, 12.2389, "Roma", "Italy"),
    "MXP": (45.6301, 8.7231, "Milán", "Italy"),
    "LHR": (51.4700, -0.4543, "Londres", "UK"),
    "LGW": (51.1537, -0.1821, "Londres Gatwick", "UK"),
    "AMS": (52.3105, 4.7683, "Ámsterdam", "Netherlands"),
    "FRA": (50.0379, 8.5622, "Frankfurt", "Germany"),
    "MUC": (48.3537, 11.7860, "Múnich", "Germany"),
    "IST": (41.2753, 28.7519, "Estambul", "Turkey"),
    "ATH": (37.9364, 23.9445, "Atenas", "Greece"),
    "VIE": (48.1103, 16.5697, "Viena", "Austria"),
    "DOH": (25.2609, 51.5651, "Doha", "Qatar"),
    "DXB": (25.2532, 55.3657, "Dubái", "UAE"),
    "AUH": (24.4330, 54.6511, "Abu Dhabi", "UAE"),
    "JFK": (40.6413, -73.7781, "Nueva York", "USA"),
    "MIA": (25.7959, -80.2870, "Miami", "USA"),
    "BOG": (4.7016, -74.1469, "Bogotá", "Colombia"),
    "EZE": (-34.8222, -58.5358, "Buenos Aires", "Argentina"),
    "MEX": (19.4361, -99.0719, "Ciudad de México", "Mexico"),
    "TYO": (35.7720, 140.3929, "Tokio", "Japan"),
    "NRT": (35.7647, 140.3863, "Tokio Narita", "Japan"),
    "HND": (35.5494, 139.7798, "Tokio Haneda", "Japan"),
    "BKK": (13.6900, 100.7501, "Bangkok", "Thailand"),
    "SIN": (1.3644, 103.9915, "Singapur", "Singapore"),
    "KUL": (2.7456, 101.7072, "Kuala Lumpur", "Malaysia"),
    "DPS": (-8.7482, 115.1672, "Bali", "Indonesia"),
    "CAI": (30.1219, 31.4056, "El Cairo", "Egypt"),
    "RAK": (31.6069, -8.0363, "Marrakech", "Morocco"),
    "KIX": (34.4347, 135.2442, "Osaka Kansai", "Japan"),
    "OSA": (34.7855, 135.4382, "Osaka", "Japan"),
}

AIRLINES_BY_HUB: Dict[str, Tuple[str, str]] = {
    "MAD": ("IB", "Iberia"),
    "BCN": ("VY", "Vueling"),
    "LIS": ("TP", "TAP Air Portugal"),
    "CDG": ("AF", "Air France"),
    "FCO": ("AZ", "ITA Airways"),
    "FRA": ("LH", "Lufthansa"),
    "AMS": ("KL", "KLM"),
    "LHR": ("BA", "British Airways"),
    "IST": ("TK", "Turkish Airlines"),
    "DOH": ("QR", "Qatar Airways"),
    "DXB": ("EK", "Emirates"),
    "JFK": ("DL", "Delta Air Lines"),
    "BKK": ("TG", "Thai Airways"),
    "SIN": ("SQ", "Singapore Airlines"),
    "TYO": ("NH", "All Nippon Airways"),
    "NRT": ("JL", "Japan Airlines"),
    "KIX": ("JL", "Japan Airlines"),
    "OSA": ("NH", "All Nippon Airways"),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great circle distance between two points in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


class MockFlightProvider(BaseFlightProvider):
    """Generates realistic, deterministic flight offers for testing and offline runs."""

    @property
    def name(self) -> str:
        return "MockProvider"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        orig = origin.upper()
        dest = destination.upper()

        orig_info = AIRPORT_COORDS.get(orig, (40.4, -3.5, orig, "Unknown"))
        dest_info = AIRPORT_COORDS.get(dest, (35.0, 139.0, dest, "Unknown"))

        distance_km = haversine_km(orig_info[0], orig_info[1], dest_info[0], dest_info[1])
        if distance_km < 100:
            distance_km = 600

        # Deterministic pseudo-random seed based on route and date
        seed_str = f"{orig}:{dest}:{travel_date.isoformat()}"
        seed_val = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)

        # Base price calculation roughly ~0.05 - 0.08 EUR per km for long haul, slightly higher for short haul
        if distance_km < 1500:
            base_price = 35.0 + (distance_km * 0.055)
            flight_time_mins = int(45 + (distance_km / 750.0) * 60)
        elif distance_km < 4000:
            base_price = 70.0 + (distance_km * 0.05)
            flight_time_mins = int(50 + (distance_km / 820.0) * 60)
        else:
            base_price = 180.0 + (distance_km * 0.042)
            flight_time_mins = int(60 + (distance_km / 880.0) * 60)

        # Day of week variation (weekends slightly higher)
        weekday = travel_date.weekday()
        day_factor = 1.15 if weekday in (4, 6) else (0.92 if weekday in (1, 2) else 1.0)

        # Route hash variation (+/- 18%)
        hash_factor = 0.88 + ((seed_val % 100) / 100.0) * 0.28
        final_base = base_price * day_factor * hash_factor

        # Select airline based on origin or destination hub
        carrier_code, carrier_name = AIRLINES_BY_HUB.get(orig, AIRLINES_BY_HUB.get(dest, ("IB", "Iberia")))

        # Generate 2 to 3 distinct flight offers
        offers: List[FlightLegOffer] = []
        flight_times = [time(7, 30), time(13, 15), time(19, 45)]

        for i in range(2):
            price = round((final_base * (1.0 + (i * 0.12))) * adults, 2)
            dep_time = flight_times[(seed_val + i) % len(flight_times)]
            dep_dt = datetime.combine(travel_date, dep_time)
            arr_dt = dep_dt + timedelta(minutes=flight_time_mins)

            seg = FlightSegment(
                carrier_code=carrier_code,
                carrier_name=carrier_name,
                flight_number=f"{carrier_code}{100 + (seed_val % 899) + i}",
                departure_airport=orig,
                arrival_airport=dest,
                departure_time=dep_dt,
                arrival_time=arr_dt,
                duration_minutes=flight_time_mins,
            )

            offer = FlightLegOffer(
                provider=self.name,
                origin=orig,
                destination=dest,
                departure_date=travel_date,
                price_eur=price,
                segments=[seg],
                total_duration_minutes=flight_time_mins,
                stops_count=0,
                airline_names=[carrier_name],
                booking_url=f"https://www.google.com/travel/flights?q=flights+from+{orig}+to+{dest}+on+{travel_date.isoformat()}",
                cabin_class="ECONOMY",
            )
            offers.append(offer)

        offers.sort(key=lambda o: o.price_eur)
        return offers
