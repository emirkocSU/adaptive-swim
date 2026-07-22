"""Feature helper tests for the ADR-039 additions (Commit 8 §12)."""

from __future__ import annotations

import math

import pytest

from swimtools.swimming_features import (
    FeatureExtractionError,
    cumulative_time_share,
    race_average_speed_mps,
    segment_speed_ratio_to_race_average,
    softmax_normalized_training_distribution,
    target_intensity_ratio,
    time_density_scale_factor,
)


def test_cumulative_time_share_is_monotonic_and_ends_at_one() -> None:
    out = cumulative_time_share([0.26, 0.24, 0.25, 0.25])
    assert out == pytest.approx([0.26, 0.50, 0.75, 1.0])
    assert all(b >= a for a, b in zip(out, out[1:], strict=False))


def test_cumulative_time_share_rejects_bad_totals() -> None:
    with pytest.raises(FeatureExtractionError):
        cumulative_time_share([0.2, 0.2])


def test_race_average_and_segment_ratio() -> None:
    avg = race_average_speed_mps(100.0, 80.0)
    assert avg == pytest.approx(1.25)
    assert segment_speed_ratio_to_race_average(1.5, avg) == pytest.approx(1.2)


def test_target_intensity_ratio() -> None:
    assert target_intensity_ratio(80.0, 72.0) == pytest.approx(0.9)


def test_time_density_scale_factor() -> None:
    assert time_density_scale_factor(80.0, 100.0) == pytest.approx(1.25)


def test_softmax_distribution_is_positive_and_sums_to_one() -> None:
    out = softmax_normalized_training_distribution([0.26, 0.24, 0.25, 0.25])
    assert all(v > 0 for v in out)
    assert math.fsum(out) == pytest.approx(1.0)


def test_softmax_distribution_shifts_with_deltas() -> None:
    base = softmax_normalized_training_distribution([0.25, 0.25, 0.25, 0.25])
    shifted = softmax_normalized_training_distribution(
        [0.25, 0.25, 0.25, 0.25], [0.3, 0.0, 0.0, 0.0]
    )
    assert shifted[0] > base[0]
    assert math.fsum(shifted) == pytest.approx(1.0)


def test_softmax_does_not_mutate_its_input() -> None:
    ratios = [0.26, 0.24, 0.25, 0.25]
    deltas = [0.1, 0.0, 0.0, 0.0]
    softmax_normalized_training_distribution(ratios, deltas)
    assert ratios == [0.26, 0.24, 0.25, 0.25]
    assert deltas == [0.1, 0.0, 0.0, 0.0]


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_softmax_rejects_non_finite_inputs(bad: float) -> None:
    with pytest.raises(FeatureExtractionError):
        softmax_normalized_training_distribution([0.5, bad])
    with pytest.raises(FeatureExtractionError):
        softmax_normalized_training_distribution([0.5, 0.5], [0.0, bad])


def test_softmax_rejects_non_positive_ratios() -> None:
    with pytest.raises(FeatureExtractionError):
        softmax_normalized_training_distribution([0.5, 0.0])


def test_softmax_rejects_length_mismatch() -> None:
    with pytest.raises(FeatureExtractionError):
        softmax_normalized_training_distribution([0.5, 0.5], [0.1])
