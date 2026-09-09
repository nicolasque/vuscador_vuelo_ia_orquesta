"""Calendar and PTO models."""

from datetime import date
from typing import List
from pydantic import BaseModel, Field


class HolidayEvent(BaseModel):
    """Represents a public holiday or weekend event."""
    event_date: date
    name: str
    is_weekend: bool = False
    is_official_holiday: bool = True


class PTOWindow(BaseModel):
    """Represents an optimized date window for travel maximizing time off."""
    start_date: date
    end_date: date
    total_days: int
    work_days_needed: int
    weekend_days: int
    holiday_days: int
    holidays_names: List[str] = Field(default_factory=list)
    efficiency_ratio: float = 1.0  # total_days / max(work_days_needed, 1)
    summary: str = ""

    @property
    def key(self) -> str:
        return f"{self.start_date.isoformat()}_{self.end_date.isoformat()}"
