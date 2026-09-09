"""Multi-Provider Pool for parallel queries, load-balancing, and automatic failover."""

import logging
from datetime import date
from typing import List
from vusca.models.flight import FlightLegOffer
from vusca.providers.base import BaseFlightProvider

logger = logging.getLogger(__name__)


class MultiProviderPool(BaseFlightProvider):
    """
    Pools multiple flight APIs together.
    - Balances requests across providers in a round-robin rotation.
    - Automatically fails over to alternate providers if one hits a rate-limit (HTTP 429) or error.
    - Speeds up large searches and avoids rate-limit bottlenecks.
    """

    def __init__(self, providers: List[BaseFlightProvider]):
        if not providers:
            raise ValueError("MultiProviderPool requires at least one provider.")
        self.providers = providers
        self._current_index = 0
        self._disabled_providers = set()

    @property
    def name(self) -> str:
        provider_names = [p.name for p in self.providers]
        return f"MultiPool ({' + '.join(provider_names)})"

    def search_leg(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        adults: int = 1,
    ) -> List[FlightLegOffer]:
        num_providers = len(self.providers)
        start_idx = self._current_index
        self._current_index = (self._current_index + 1) % num_providers

        last_error = None

        # Try providers in circular order starting from the assigned round-robin index
        for offset in range(num_providers):
            p_idx = (start_idx + offset) % num_providers
            provider = self.providers[p_idx]

            # Skip provider if marked quota-exhausted and other providers exist
            if provider.name in self._disabled_providers and len(self._disabled_providers) < num_providers:
                continue

            try:
                offers = provider.search_leg(origin, destination, travel_date, adults=adults)
                if offers:
                    return offers
            except Exception as e:
                last_error = e
                err_lower = str(e).lower()
                if "monthly quota" in err_lower or "quota exceeded" in err_lower:
                    logger.warning(f"Provider {provider.name} exceeded quota. Disabling in pool.")
                    self._disabled_providers.add(provider.name)
                else:
                    logger.warning(
                        f"Provider {provider.name} failed for {origin}➔{destination} on {travel_date}: {e}. "
                        f"Failing over to next available provider in pool..."
                    )
                continue

        # If all real providers failed or returned empty, raise last error
        if last_error:
            raise last_error
        return []
