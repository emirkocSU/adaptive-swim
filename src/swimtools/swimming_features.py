"""Pure feature-extraction helpers for swimming performance data (ADR-038 §22).

Every function is pure and deterministic: it mutates nothing, uses no clock/randomness/IO,
and rejects NaN/infinity, zero denominators and negative physical inputs rather than
returning a silently-wrong number. Missingness is never guessed here — a caller with missing
data must not call these.

IMU integration and load–velocity regression are intentionally NOT implemented; they remain
in the research backlog (docs/data), not in the runtime.
"""

from __future__ import annotations

import math


class FeatureExtractionError(ValueError):
    """A feature could not be computed from the given inputs (invalid/degenerate)."""


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeatureExtractionError(f"{label} must be a real number, got {value!r}")
    if not math.isfinite(value):
        raise FeatureExtractionError(f"{label} must be finite, got {value}")
    return float(value)


def _positive(value: float, label: str) -> float:
    v = _finite(value, label)
    if v <= 0.0:
        raise FeatureExtractionError(f"{label} must be > 0, got {v}")
    return v


def _non_negative(value: float, label: str) -> float:
    v = _finite(value, label)
    if v < 0.0:
        raise FeatureExtractionError(f"{label} must be >= 0, got {v}")
    return v


def split_speed_mps(split_distance_m: float, split_time_sec: float) -> float:
    """Mean speed over a split: ``distance / time`` (m/s)."""
    d = _positive(split_distance_m, "split_distance_m")
    t = _positive(split_time_sec, "split_time_sec")
    return d / t


def cumulative_times_sec(split_times_sec: list[float]) -> list[float]:
    """Running cumulative sum of split times (does not mutate the input)."""
    out: list[float] = []
    running = 0.0
    for i, t in enumerate(split_times_sec):
        running += _non_negative(t, f"split_times_sec[{i}]")
        out.append(running)
    return out


def split_ratios(split_times_sec: list[float], total_time_sec: float) -> list[float]:
    """Each split time as a fraction of the total (does not mutate the input)."""
    total = _positive(total_time_sec, "total_time_sec")
    return [
        _non_negative(t, f"split_times_sec[{i}]") / total for i, t in enumerate(split_times_sec)
    ]


def velocity_from_position_time(
    previous_distance_m: float,
    current_distance_m: float,
    previous_time_sec: float,
    current_time_sec: float,
) -> float:
    """Average velocity between two position/time samples (m/s)."""
    d0 = _finite(previous_distance_m, "previous_distance_m")
    d1 = _finite(current_distance_m, "current_distance_m")
    t0 = _finite(previous_time_sec, "previous_time_sec")
    t1 = _finite(current_time_sec, "current_time_sec")
    dt = t1 - t0
    if dt <= 0.0:
        raise FeatureExtractionError(f"time must advance: {t1} <= {t0}")
    dd = d1 - d0
    if dd < 0.0:
        raise FeatureExtractionError(f"distance must not decrease: {d1} < {d0}")
    return dd / dt


def clean_swimming_speed_mps(
    free_swimming_distance_m: float,
    free_swimming_time_sec: float,
) -> float:
    """Speed over the free-swimming (non-turn, non-start) portion (m/s)."""
    d = _positive(free_swimming_distance_m, "free_swimming_distance_m")
    t = _positive(free_swimming_time_sec, "free_swimming_time_sec")
    return d / t


def stroke_length_m_per_cycle(
    free_swimming_distance_m: float,
    stroke_count: float,
) -> float:
    """Distance per stroke cycle over the free-swimming portion (m/cycle)."""
    d = _positive(free_swimming_distance_m, "free_swimming_distance_m")
    n = _positive(stroke_count, "stroke_count")
    return d / n


def stroke_rate_cycles_per_min(
    stroke_count: float,
    free_swimming_time_sec: float,
) -> float:
    """Stroke cycles per minute over the free-swimming portion."""
    n = _non_negative(stroke_count, "stroke_count")
    t = _positive(free_swimming_time_sec, "free_swimming_time_sec")
    return n / t * 60.0


def stroke_index(
    clean_swimming_speed_mps_value: float,
    stroke_length_m_per_cycle_value: float,
) -> float:
    """Stroke index = clean swimming speed × stroke length (m²/(s·cycle))."""
    v = _positive(clean_swimming_speed_mps_value, "clean_swimming_speed_mps")
    sl = _positive(stroke_length_m_per_cycle_value, "stroke_length_m_per_cycle")
    return v * sl


__all__ = [
    "FeatureExtractionError",
    "clean_swimming_speed_mps",
    "cumulative_times_sec",
    "split_ratios",
    "split_speed_mps",
    "stroke_index",
    "stroke_length_m_per_cycle",
    "stroke_rate_cycles_per_min",
    "velocity_from_position_time",
]
