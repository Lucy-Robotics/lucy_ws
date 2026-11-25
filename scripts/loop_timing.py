from typing import Dict, List, Sequence


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1) + 0.5))]


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 3)


def loop_timing_summary(stamps: Sequence[float], rate_hz: float) -> Dict[str, float]:
    period = 1.0 / rate_hz
    periods: List[float] = [b - a for a, b in zip(stamps, stamps[1:]) if b > a]
    if not periods:
        raise ValueError("need at least two increasing stamps")
    phase = [abs(p - round(p / period) * period) for p in periods]
    return {
        "samples": len(periods),
        "period_p50_ms": _ms(_percentile(periods, 0.5)),
        "period_p99_ms": _ms(_percentile(periods, 0.99)),
        "period_max_ms": _ms(max(periods)),
        "phase_jitter_p99_ms": _ms(_percentile(phase, 0.99)),
        "phase_jitter_max_ms": _ms(max(phase)),
        "late_cycles": sum(1 for p in periods if p >= 1.5 * period),
    }
