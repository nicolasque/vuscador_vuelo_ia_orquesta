"""AeroDataBox API Provider via RapidAPI (aerodatabox.p.rapidapi.com)."""

import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class AeroDataBoxClient:
    """Client connecting to AeroDataBox on RapidAPI for aviation operations and quota monitoring."""

    def __init__(
        self,
        api_key: str,
        api_host: str = "aerodatabox.p.rapidapi.com",
    ):
        self.api_key = api_key
        self.api_host = api_host
        self.base_url = f"https://{self.api_host}"

    def check_balance(self) -> Dict[str, Any]:
        """Queries remaining subscription balance and rate limits."""
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.api_host,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/subscriptions/balance"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            return {
                "status_code": resp.status_code,
                "requests_limit": resp.headers.get("x-ratelimit-requests-limit"),
                "requests_remaining": resp.headers.get("x-ratelimit-requests-remaining"),
                "api_units_limit": resp.headers.get("x-ratelimit-api-units-limit"),
                "api_units_remaining": resp.headers.get("x-ratelimit-api-units-remaining"),
            }
        except Exception as e:
            logger.warning(f"AeroDataBox balance check failed: {e}")
            return {"error": str(e)}
