"""Flight models representing legs, offers and multi-city itineraries."""

from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class FlightSegment(BaseModel):
    """Represents a single flight hopping from one airport to another."""
    carrier_code: str
    carrier_name: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int


class FlightLegOffer(BaseModel):
    """Represents an offer for a specific travel leg (e.g. MAD -> IST on 2026-10-12)."""
    provider: str
    origin: str
    destination: str
    departure_date: date
    price_eur: float
    segments: List[FlightSegment] = Field(default_factory=list)
    total_duration_minutes: int = 0
    stops_count: int = 0
    airline_names: List[str] = Field(default_factory=list)
    booking_url: Optional[str] = None
    cabin_class: str = "ECONOMY"

    @property
    def flight_search_url(self) -> str:
        """Returns direct booking URL or generates a Google Flights search link."""
        if self.booking_url:
            return self.booking_url
        d_str = self.departure_date.isoformat() if hasattr(self.departure_date, 'isoformat') else str(self.departure_date)
        return f"https://www.google.com/travel/flights?q=flights+from+{self.origin}+to+{self.destination}+on+{d_str}"

    @model_validator(mode="after")
    def compute_stops_count(self) -> "FlightLegOffer":
        if self.segments and len(self.segments) > 1:
            self.stops_count = max(self.stops_count, len(self.segments) - 1)
        return self

    @property
    def key(self) -> str:
        return f"{self.origin}-{self.destination}-{self.departure_date.isoformat()}"


class StopoverDetail(BaseModel):
    """Details about an intermediate stop in a city during the itinerary."""
    city_code: str
    city_name: str
    stay_days: int
    arrival_date: date
    departure_date: date
    highlights: Optional[str] = None


class Itinerary(BaseModel):
    """A full multi-city trip itinerary combining multiple flight legs."""
    itinerary_id: str
    origin: str
    final_destination: str
    start_date: date
    end_date: date
    legs: List[FlightLegOffer] = Field(default_factory=list)
    stopovers: List[StopoverDetail] = Field(default_factory=list)
    total_price_eur: float = 0.0
    total_trip_days: int = 0
    work_days_needed: int = 0
    pto_efficiency_ratio: float = 1.0
    ai_score: float = 0.0
    ai_verdict: str = ""
    route_summary: str = ""

    def calculate_totals(self, work_days: int = 0):
        self.total_price_eur = round(sum(leg.price_eur for leg in self.legs), 2)
        self.total_trip_days = (self.end_date - self.start_date).days + 1
        self.work_days_needed = work_days
        self.pto_efficiency_ratio = round(
            self.total_trip_days / max(self.work_days_needed, 1), 2
        )
