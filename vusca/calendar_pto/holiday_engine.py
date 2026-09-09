"""Holiday and PTO Optimization Engine.

Identifies public holidays, long weekends (puentes), and calculates high-efficiency
travel windows to maximize continuous vacation days while minimizing PTO used.
"""

from datetime import date, timedelta
from typing import List, Optional, Dict, Tuple
import holidays

from vusca.models.calendar import PTOWindow, HolidayEvent


class HolidayEngine:
    def __init__(self, country: str = "ES", subdiv: Optional[str] = "MD"):
        self.country = country.upper()
        self.subdiv = subdiv.upper() if subdiv else None
        self._holidays_cache: Dict[int, holidays.HolidayBase] = {}

    def get_holidays(self, year: int) -> holidays.HolidayBase:
        if year not in self._holidays_cache:
            try:
                self._holidays_cache[year] = holidays.country_holidays(
                    self.country,
                    subdiv=self.subdiv,
                    years=year
                )
            except Exception:
                # Fallback to no subdivision if subdiv fails
                self._holidays_cache[year] = holidays.country_holidays(
                    self.country,
                    years=year
                )
        return self._holidays_cache[year]

    def is_holiday(self, day: date) -> Tuple[bool, Optional[str]]:
        h_dict = self.get_holidays(day.year)
        if day in h_dict:
            return True, h_dict[day]
        return False, None

    def is_working_day(self, day: date) -> bool:
        # 5 = Saturday, 6 = Sunday
        if day.weekday() in (5, 6):
            return False
        is_hol, _ = self.is_holiday(day)
        return not is_hol

    def get_holiday_events_in_range(self, start_date: date, end_date: date) -> List[HolidayEvent]:
        events = []
        curr = start_date
        while curr <= end_date:
            is_hol, name = self.is_holiday(curr)
            is_wknd = curr.weekday() in (5, 6)
            if is_hol:
                events.append(
                    HolidayEvent(
                        event_date=curr,
                        name=name or "Festivo",
                        is_weekend=is_wknd,
                        is_official_holiday=True,
                    )
                )
            curr += timedelta(days=1)
        return events

    def find_optimal_windows(
        self,
        start_search: date,
        end_search: date,
        max_pto_days: int = 5,
        min_total_days: int = 5,
        max_total_days: int = 21,
        top_k: int = 5,
    ) -> List[PTOWindow]:
        """
        Scans date ranges within [start_search, end_search] to find windows that
        require <= max_pto_days of work leave, while maximizing the total days off.
        """
        candidate_windows: List[PTOWindow] = []
        
        # Precompute day statuses for speed up to end_search + max_total_days
        max_horizon = end_search + timedelta(days=max_total_days + 3)
        day_map: Dict[date, Tuple[bool, bool, Optional[str]]] = {}
        curr = start_search - timedelta(days=2)
        while curr <= max_horizon:
            is_wknd = curr.weekday() in (5, 6)
            is_hol, hol_name = self.is_holiday(curr)
            is_work = (not is_wknd) and (not is_hol)
            day_map[curr] = (is_work, is_wknd, hol_name)
            curr += timedelta(days=1)

        total_search_days = (end_search - start_search).days + 1

        for i in range(total_search_days):
            start = start_search + timedelta(days=i)
            # Generally best travel windows start on Saturday (or Friday afternoon / Thursday holiday)
            for length in range(min_total_days, max_total_days + 1):
                end = start + timedelta(days=length - 1)

                work_days = 0
                weekend_days = 0
                holiday_days = 0
                holidays_included = []

                day_cursor = start
                while day_cursor <= end:
                    is_work, is_wknd, hol_name = day_map.get(
                        day_cursor,
                        (not (day_cursor.weekday() in (5, 6)), day_cursor.weekday() in (5, 6), None)
                    )
                    if is_work:
                        work_days += 1
                    else:
                        if is_wknd:
                            weekend_days += 1
                        if hol_name:
                            holiday_days += 1
                            if hol_name not in holidays_included:
                                holidays_included.append(f"{hol_name} ({day_cursor.strftime('%d/%m')})")
                    day_cursor += timedelta(days=1)

                if 1 <= work_days <= max_pto_days:
                    # Prefer windows that start and end on non-working days
                    start_is_work = day_map[start][0]
                    end_is_work = day_map[end][0]
                    
                    # Bonus for starting/ending on weekend or holiday
                    edge_bonus = 0.0
                    if not start_is_work:
                        edge_bonus += 0.25
                    if not end_is_work:
                        edge_bonus += 0.25

                    ratio = (length / work_days) + edge_bonus
                    
                    summary = (
                        f"{length} días de viaje usando solo {work_days} días de vacaciones "
                        f"(Eficiencia x{round(length / work_days, 1)})"
                    )
                    if holidays_included:
                        summary += f" - Aprovecha: {', '.join(holidays_included)}"

                    candidate_windows.append(
                        PTOWindow(
                            start_date=start,
                            end_date=end,
                            total_days=length,
                            work_days_needed=work_days,
                            weekend_days=weekend_days,
                            holiday_days=holiday_days,
                            holidays_names=holidays_included,
                            efficiency_ratio=round(ratio, 2),
                            summary=summary,
                        )
                    )

        # Sort candidate windows: higher efficiency first, then more total days, then fewer work days
        candidate_windows.sort(
            key=lambda w: (w.efficiency_ratio, w.total_days, -w.work_days_needed),
            reverse=True,
        )

        # Filter duplicates or heavily overlapping windows to ensure variety
        distinct_windows: List[PTOWindow] = []
        for win in candidate_windows:
            # Check overlap with existing
            is_overlap = False
            for accepted in distinct_windows:
                # If they share more than 60% of dates, consider it redundant
                overlap_start = max(win.start_date, accepted.start_date)
                overlap_end = min(win.end_date, accepted.end_date)
                if overlap_start <= overlap_end:
                    overlap_days = (overlap_end - overlap_start).days + 1
                    if overlap_days / min(win.total_days, accepted.total_days) > 0.6:
                        is_overlap = True
                        break
            if not is_overlap:
                distinct_windows.append(win)
            if len(distinct_windows) >= top_k:
                break

        return distinct_windows

    def calculate_window_for_dates(self, start: date, end: date) -> Optional[PTOWindow]:
        """Computes PTOWindow metrics for an explicit start and end date."""
        if start > end:
            return None
        length = (end - start).days + 1
        work_days = 0
        weekend_days = 0
        holiday_days = 0
        holidays_included = []

        curr = start
        while curr <= end:
            is_hol, hol_name = self.is_holiday(curr)
            is_wknd = curr.weekday() in (5, 6)
            is_work = (not is_wknd) and (not is_hol)
            if is_work:
                work_days += 1
            else:
                if is_wknd:
                    weekend_days += 1
                if hol_name:
                    holiday_days += 1
                    if hol_name not in holidays_included:
                        holidays_included.append(f"{hol_name} ({curr.strftime('%d/%m')})")
            curr += timedelta(days=1)

        start_is_work = (start.weekday() not in (5, 6)) and (not self.is_holiday(start)[0])
        end_is_work = (end.weekday() not in (5, 6)) and (not self.is_holiday(end)[0])
        edge_bonus = (0.25 if not start_is_work else 0.0) + (0.25 if not end_is_work else 0.0)

        effective_work_days = max(work_days, 1)
        ratio = (length / effective_work_days) + edge_bonus

        summary = (
            f"{length} días de viaje usando {work_days} días de vacaciones "
            f"(Eficiencia x{round(length / effective_work_days, 1)})"
        )
        if holidays_included:
            summary += f" - Aprovecha: {', '.join(holidays_included)}"

        return PTOWindow(
            start_date=start,
            end_date=end,
            total_days=length,
            work_days_needed=work_days,
            weekend_days=weekend_days,
            holiday_days=holiday_days,
            holidays_names=holidays_included,
            efficiency_ratio=round(ratio, 2),
            summary=summary,
        )

    def generate_flexible_variations(
        self,
        base_windows: List[PTOWindow],
        flexibility_days: int = 1,
        max_pto_days: int = 15,
        min_total_days: int = 5,
        max_total_days: int = 30,
    ) -> List[PTOWindow]:
        """
        Generates departure and return variations (e.g. +/- 1, 2 days)
        for given base windows, filtering by budget of PTO days and trip length.
        """
        variations: Dict[Tuple[date, date], PTOWindow] = {}

        for base in base_windows:
            for d_offset in range(-flexibility_days, flexibility_days + 1):
                for r_offset in range(-flexibility_days, flexibility_days + 1):
                    new_start = base.start_date + timedelta(days=d_offset)
                    new_end = base.end_date + timedelta(days=r_offset)
                    pair = (new_start, new_end)
                    if pair in variations:
                        continue

                    win = self.calculate_window_for_dates(new_start, new_end)
                    if win and win.work_days_needed <= max_pto_days:
                        if min_total_days <= win.total_days <= max_total_days:
                            variations[pair] = win

        sorted_wins = list(variations.values())
        sorted_wins.sort(key=lambda w: (w.efficiency_ratio, w.total_days, -w.work_days_needed), reverse=True)
        return sorted_wins
