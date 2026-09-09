"""Abstract Base Provider for flight searches."""

from abc import ABC, abstractmethod
from datetime import date
from typing import List
from vusca.models.flight import FlightLegOffer


class BaseFlightProvider(ABC):
    """Abstract interface that all flight API providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g. 'Amadeus', 'Kiwi', 'Mock')."""
        pass

    @abstractmethod
    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        """
        Search for one-way flight offers from origin to destination on travel_date.
        Returns a list of FlightLegOffer objects sorted by price ascending.
        """
        pass
