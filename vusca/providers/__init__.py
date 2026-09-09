"""Flight Providers module."""

import logging
from typing import Optional

from vusca.providers.base import BaseFlightProvider
from vusca.providers.mock import MockFlightProvider
from vusca.providers.amadeus import AmadeusProvider
from vusca.providers.kiwi import KiwiProvider
from vusca.providers.rapidapi import RapidApiFlightProvider
from vusca.providers.google_flights import GoogleFlightsProvider
from vusca.providers.skyscanner4 import SkyscannerFlights4Provider
from vusca.providers.flights_scraper import FlightsScraperDataProvider
from vusca.providers.kiwi_rapid import KiwiRapidProvider
from vusca.providers.aerodatabox import AeroDataBoxClient
from vusca.providers.duffel import DuffelProvider
from vusca.providers.pool import MultiProviderPool
from vusca import config

logger = logging.getLogger(__name__)


def get_available_real_providers() -> list:
    """Detects all providers that have credentials set in the environment."""
    active = []
    # Primary Google Flights provider (150 calls/month)
    if config.GOOGLE_FLIGHTS_API_KEYS:
        active.append(GoogleFlightsProvider(config.GOOGLE_FLIGHTS_API_KEYS, config.GOOGLE_FLIGHTS_HOST))
    # Skyscanner Flights 4 provider (100 calls/month)
    if config.SKYSCANNER4_API_KEYS:
        active.append(SkyscannerFlights4Provider(config.SKYSCANNER4_API_KEYS, config.SKYSCANNER4_HOST))
    # Skyscanner Legacy
    if config.RAPIDAPI_KEYS:
        active.append(RapidApiFlightProvider(config.RAPIDAPI_KEYS[0], config.RAPIDAPI_HOST))
    if config.KIWI_API_KEY:
        active.append(KiwiProvider(config.KIWI_API_KEY))
    if config.DUFFEL_API_KEY:
        active.append(DuffelProvider(config.DUFFEL_API_KEY))
    if config.AMADEUS_CLIENT_ID and config.AMADEUS_CLIENT_SECRET:
        active.append(
            AmadeusProvider(
                config.AMADEUS_CLIENT_ID,
                config.AMADEUS_CLIENT_SECRET,
                config.AMADEUS_ENV,
            )
        )
    return active


def get_flight_provider(override_name: Optional[str] = None) -> BaseFlightProvider:
    """Factory to get the appropriate flight provider or multi-provider pool."""
    choice = (override_name or config.FLIGHT_PROVIDER).lower()

    if choice == "kiwi":
        if config.KIWI_API_KEY:
            return KiwiProvider(config.KIWI_API_KEY)
        logger.warning("Kiwi API key missing, falling back to MockProvider.")

    elif choice in ("google", "google-flights", "google_flights"):
        if config.GOOGLE_FLIGHTS_API_KEYS:
            return GoogleFlightsProvider(config.GOOGLE_FLIGHTS_API_KEYS, config.GOOGLE_FLIGHTS_HOST)
        logger.warning("Google Flights API key missing, falling back to MockProvider.")

    elif choice in ("skyscanner4", "skyscanner-flights4", "skyscanner"):
        if config.SKYSCANNER4_API_KEYS:
            return SkyscannerFlights4Provider(config.SKYSCANNER4_API_KEYS, config.SKYSCANNER4_HOST)
        logger.warning("Skyscanner4 API key missing, falling back to MockProvider.")

    elif choice in ("scraper", "flights-scraper", "flights_scraper"):
        if config.FLIGHTS_SCRAPER_API_KEY:
            return FlightsScraperDataProvider(config.FLIGHTS_SCRAPER_API_KEY, config.FLIGHTS_SCRAPER_HOST)
        logger.warning("FlightsScraper API key missing, falling back to MockProvider.")

    elif choice in ("kiwi-rapid", "kiwi_rapid"):
        if config.KIWI_RAPID_API_KEY:
            return KiwiRapidProvider(config.KIWI_RAPID_API_KEY, config.KIWI_RAPID_HOST)
        logger.warning("KiwiRapid API key missing, falling back to MockProvider.")

    elif choice == "rapidapi":
        if config.RAPIDAPI_KEY:
            return RapidApiFlightProvider(config.RAPIDAPI_KEY, config.RAPIDAPI_HOST)
        logger.warning("RapidAPI key missing, falling back to MockProvider.")

    elif choice == "duffel":
        if config.DUFFEL_API_KEY:
            return DuffelProvider(config.DUFFEL_API_KEY)
        logger.warning("Duffel API key missing, falling back to MockProvider.")

    elif choice == "amadeus":
        if config.AMADEUS_CLIENT_ID and config.AMADEUS_CLIENT_SECRET:
            return AmadeusProvider(
                config.AMADEUS_CLIENT_ID,
                config.AMADEUS_CLIENT_SECRET,
                config.AMADEUS_ENV,
            )
        logger.warning("Amadeus credentials missing, falling back to MockProvider.")

    elif choice in ("auto", "pool"):
        active = get_available_real_providers()
        if len(active) > 1:
            logger.info(f"Using MultiProviderPool with {len(active)} active providers.")
            return MultiProviderPool(active)
        elif len(active) == 1:
            return active[0]
        elif choice == "pool":
            # If user explicitly requested pool but no external keys, create a 2-node mock pool for testing
            p1 = MockFlightProvider()
            p2 = MockFlightProvider()
            return MultiProviderPool([p1, p2])

    # Default fallback
    return MockFlightProvider()


__all__ = [
    "BaseFlightProvider",
    "MockFlightProvider",
    "AmadeusProvider",
    "KiwiProvider",
    "RapidApiFlightProvider",
    "GoogleFlightsProvider",
    "SkyscannerFlights4Provider",
    "FlightsScraperDataProvider",
    "KiwiRapidProvider",
    "AeroDataBoxClient",
    "DuffelProvider",
    "MultiProviderPool",
    "get_flight_provider",
]
