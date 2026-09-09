"""Data models for Vusca."""

from vusca.models.flight import FlightSegment, FlightLegOffer, StopoverDetail, Itinerary
from vusca.models.calendar import HolidayEvent, PTOWindow
from vusca.models.search import SearchJob, SearchLegTask

__all__ = [
    "FlightSegment",
    "FlightLegOffer",
    "StopoverDetail",
    "Itinerary",
    "HolidayEvent",
    "PTOWindow",
    "SearchJob",
    "SearchLegTask",
]
