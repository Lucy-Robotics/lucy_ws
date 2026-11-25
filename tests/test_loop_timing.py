import pytest

from scripts.loop_timing import loop_timing_summary


def steady(count, period, start=100.0):
    return [start + i * period for i in range(count)]


def test_steady_100_hz_loop_has_no_jitter_and_no_late_cycles():
    summary = loop_timing_summary(steady(201, 0.01), 100)
    assert summary["samples"] == 200
    assert summary["period_p50_ms"] == pytest.approx(10.0, abs=1e-6)
    assert summary["phase_jitter_max_ms"] == pytest.approx(0.0, abs=1e-6)
    assert summary["late_cycles"] == 0


def test_windows_default_tick_shows_as_late_cycles_and_large_jitter():
    summary = loop_timing_summary(steady(101, 0.015625), 100)
    assert summary["period_p50_ms"] == pytest.approx(15.625, abs=1e-3)
    assert summary["late_cycles"] == 100
    assert summary["phase_jitter_p99_ms"] == pytest.approx(4.375, abs=1e-3)


def test_one_dropped_message_counts_as_one_late_cycle_without_phase_jitter():
    stamps = steady(50, 0.01) + steady(50, 0.01, start=100.0 + 51 * 0.01)
    summary = loop_timing_summary(stamps, 100)
    assert summary["late_cycles"] == 1
    assert summary["period_max_ms"] == pytest.approx(20.0, abs=1e-6)
    assert summary["phase_jitter_max_ms"] == pytest.approx(0.0, abs=1e-6)


def test_repeated_or_reordered_stamps_are_ignored():
    summary = loop_timing_summary([1.0, 1.0, 1.01, 1.005, 1.02], 100)
    assert summary["samples"] == 2


def test_fewer_than_two_stamps_is_an_error():
    with pytest.raises(ValueError):
        loop_timing_summary([1.0], 100)
