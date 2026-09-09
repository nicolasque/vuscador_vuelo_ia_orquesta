"""Tests for MultiProviderPool load-balancing and failover."""

from datetime import date
from vusca.providers.mock import MockFlightProvider
from vusca.providers.pool import MultiProviderPool
from vusca.providers.base import BaseFlightProvider


class FailingProvider(BaseFlightProvider):
    @property
    def name(self) -> str:
        return "FailingProvider"

    def search_leg(self, origin: str, destination: str, travel_date: date, adults: int = 1):
        raise RuntimeError("API Rate limit 429")


def test_multi_provider_pool_failover():
    failing = FailingProvider()
    working = MockFlightProvider()

    # Even if the first provider in pool fails, it should seamlessly failover to the working one
    pool = MultiProviderPool([failing, working])

    offers = pool.search_leg("MAD", "TYO", date(2027, 3, 19))
    assert len(offers) > 0
    assert offers[0].origin == "MAD"
    assert offers[0].destination == "TYO"


def test_multi_provider_pool_round_robin():
    p1 = MockFlightProvider()
    p2 = MockFlightProvider()
    pool = MultiProviderPool([p1, p2])

    # Round robin index should rotate
    assert pool._current_index == 0
    pool.search_leg("MAD", "IST", date(2027, 3, 19))
    assert pool._current_index == 1
    pool.search_leg("IST", "TYO", date(2027, 3, 21))
    assert pool._current_index == 0
