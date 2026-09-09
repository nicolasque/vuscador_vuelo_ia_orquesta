"""Tests for HolidayEngine."""

from datetime import date
from vusca.calendar_pto.holiday_engine import HolidayEngine


def test_holiday_engine_detection():
    # Test Spanish holidays in Madrid
    engine = HolidayEngine(country="ES", subdiv="MD")
    
    # 2026-10-12 is Fiesta Nacional de España
    is_hol, name = engine.is_holiday(date(2026, 10, 12))
    assert is_hol is True
    assert name is not None
    assert "Fiesta Nacional" in name or "Hispanidad" in name or "Pilar" in name or "España" in name or len(name) > 0


def test_find_optimal_windows():
    engine = HolidayEngine(country="ES", subdiv="MD")
    
    # Search around October 2026 (including 12 Oct)
    windows = engine.find_optimal_windows(
        start_search=date(2026, 10, 1),
        end_search=date(2026, 10, 31),
        max_pto_days=5,
        min_total_days=5,
        max_total_days=10,
        top_k=3,
    )
    
    assert len(windows) > 0
    top = windows[0]
    assert top.work_days_needed <= 5
    assert top.efficiency_ratio >= 1.5
    assert top.total_days >= top.work_days_needed


def test_generate_flexible_variations():
    engine = HolidayEngine(country="ES", subdiv="MD")
    base_windows = engine.find_optimal_windows(
        start_search=date(2027, 3, 15),
        end_search=date(2027, 4, 15),
        max_pto_days=15,
        min_total_days=18,
        max_total_days=25,
        top_k=2,
    )
    assert len(base_windows) > 0

    flexible = engine.generate_flexible_variations(
        base_windows=base_windows,
        flexibility_days=1,
        max_pto_days=15,
        min_total_days=18,
        max_total_days=25,
    )
    # Should include base windows plus ±1 day shifts
    assert len(flexible) >= len(base_windows)
    for fw in flexible:
        assert fw.work_days_needed <= 15
        assert 18 <= fw.total_days <= 25

