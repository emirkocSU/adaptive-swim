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
    if isinstance(value, bool) or not isinstance(value, int | float):
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


# --------------------------------------------------------------------------- ADR-039 helpers
#: Central epsilon for log/softmax stabilisation in the training-distribution helper.
RATIO_EPSILON: float = 1e-9

#: Tolerance for "ratios sum to one" checks.
RATIO_SUM_TOLERANCE: float = 1e-6


def cumulative_time_share(split_time_shares: list[float]) -> list[float]:
    """Running sum of per-segment time shares (each in (0, 1], total ≈ 1).

    The input is not mutated. Non-finite, non-positive or badly-summing shares raise.
    """
    if not split_time_shares:
        raise FeatureExtractionError("split_time_shares must be non-empty")
    shares = [_positive(v, "split_time_share") for v in split_time_shares]
    total = math.fsum(shares)
    if abs(total - 1.0) > 1e-3:
        raise FeatureExtractionError(f"time shares must sum to ~1, got {total}")
    out: list[float] = []
    running = 0.0
    for share in shares:
        running += share
        out.append(running)
    return out


def race_average_speed_mps(total_distance_m: float, total_time_sec: float) -> float:
    """Mean race speed: ``total distance / total time`` (m/s)."""
    d = _positive(total_distance_m, "total_distance_m")
    t = _positive(total_time_sec, "total_time_sec")
    return d / t


def segment_speed_ratio_to_race_average(
    segment_speed_mps_value: float, race_average_speed_mps_value: float
) -> float:
    """Segment speed expressed as a ratio of the race average (1.0 = exactly average)."""
    v = _positive(segment_speed_mps_value, "segment_speed_mps")
    avg = _positive(race_average_speed_mps_value, "race_average_speed_mps")
    return v / avg


def target_intensity_ratio(target_time_sec: float, reference_best_time_sec: float) -> float:
    """Training intensity as ``reference best / target`` (1.0 = at reference pace).

    Values below 1.0 mean the target is slower than the reference best; the helper never
    invents a physiological interpretation.
    """
    target = _positive(target_time_sec, "target_time_sec")
    reference = _positive(reference_best_time_sec, "reference_best_time_sec")
    return reference / target


def softmax_normalized_training_distribution(
    race_ratios: list[float],
    training_deltas: list[float] | None = None,
    *,
    epsilon: float = RATIO_EPSILON,
) -> list[float]:
    """``p_train[i] = softmax(log(p_race[i] + eps) + delta_train[i])``.

    A small, regularized correction of a coarse race split prior toward the training
    domain. Inputs are positive ratios; the output ratios are positive and sum to 1 within
    tolerance. Inputs are never mutated; NaN/infinity are rejected.
    """
    if not race_ratios:
        raise FeatureExtractionError("race_ratios must be non-empty")
    ratios = [_positive(v, "race_ratio") for v in race_ratios]
    if training_deltas is None:
        deltas = [0.0] * len(ratios)
    else:
        if len(training_deltas) != len(ratios):
            raise FeatureExtractionError(
                f"training_deltas length {len(training_deltas)} != race_ratios length {len(ratios)}"
            )
        deltas = [_finite(v, "training_delta") for v in training_deltas]
    eps = _positive(epsilon, "epsilon")
    logits = [math.log(r + eps) + d for r, d in zip(ratios, deltas, strict=True)]
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = math.fsum(exps)
    if total <= 0.0 or not math.isfinite(total):
        raise FeatureExtractionError("softmax normalisation degenerated")
    out = [e / total for e in exps]
    if abs(math.fsum(out) - 1.0) > RATIO_SUM_TOLERANCE:
        raise FeatureExtractionError("normalized training distribution does not sum to 1")
    if any(v <= 0.0 for v in out):
        raise FeatureExtractionError("normalized training distribution must be strictly positive")
    return out


def time_density_scale_factor(
    reference_total_time_sec: float, target_total_time_sec: float
) -> float:
    """Uniform time-density scale between a reference plan and a target total time.

    Used to reason about how a coarse prior stretches or compresses before the exact
    deterministic reconciliation runs — it is NOT itself a reconciliation.
    """
    reference = _positive(reference_total_time_sec, "reference_total_time_sec")
    target = _positive(target_total_time_sec, "target_total_time_sec")
    return target / reference


__all__ = [
    "RATIO_EPSILON",
    "RATIO_SUM_TOLERANCE",
    "FeatureExtractionError",
    "cumulative_time_share",
    "race_average_speed_mps",
    "segment_speed_ratio_to_race_average",
    "softmax_normalized_training_distribution",
    "target_intensity_ratio",
    "time_density_scale_factor",
    "clean_swimming_speed_mps",
    "cumulative_times_sec",
    "split_ratios",
    "split_speed_mps",
    "stroke_index",
    "stroke_length_m_per_cycle",
    "stroke_rate_cycles_per_min",
    "velocity_from_position_time",
]
