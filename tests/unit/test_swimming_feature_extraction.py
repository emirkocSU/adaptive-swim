"""Pure feature-extraction tests (Commit 8 §22, §37)."""

from __future__ import annotations

import pytest

from swimtools.swimming_features import (
    FeatureExtractionError,
    clean_swimming_speed_mps,
    cumulative_times_sec,
    split_ratios,
    split_speed_mps,
    stroke_index,
    stroke_length_m_per_cycle,
    stroke_rate_cycles_per_min,
    velocity_from_position_time,
)


def test_split_speed() -> None:
    assert split_speed_mps(50.0, 40.0) == 1.25


def test_cumulative_times() -> None:
    assert cumulative_times_sec([20.0, 21.0, 22.0]) == [20.0, 41.0, 63.0]


def test_cumulative_does_not_mutate() -> None:
    data = [10.0, 11.0]
    cumulative_times_sec(data)
    assert data == [10.0, 11.0]


def test_split_ratios() -> None:
    ratios = split_ratios([20.0, 30.0], 50.0)
    assert ratios == [0.4, 0.6]


def test_velocity_from_position_time() -> None:
    assert velocity_from_position_time(10.0, 20.0, 5.0, 13.0) == 1.25


def test_clean_swimming_speed() -> None:
    assert clean_swimming_speed_mps(35.0, 25.0) == 1.4


def test_stroke_length() -> None:
    assert stroke_length_m_per_cycle(40.0, 20.0) == 2.0


def test_stroke_rate() -> None:
    assert stroke_rate_cycles_per_min(30.0, 60.0) == 30.0


def test_stroke_index() -> None:
    assert stroke_index(1.4, 2.0) == pytest.approx(2.8)


@pytest.mark.parametrize(
    "fn,args",
    [
        (split_speed_mps, (50.0, 0.0)),
        (split_speed_mps, (0.0, 40.0)),
        (split_speed_mps, (-50.0, 40.0)),
        (clean_swimming_speed_mps, (35.0, 0.0)),
        (stroke_length_m_per_cycle, (40.0, 0.0)),
        (stroke_rate_cycles_per_min, (30.0, 0.0)),
        (stroke_index, (0.0, 2.0)),
    ],
)
def test_rejects_zero_or_negative(fn, args) -> None:  # noqa: ANN001
    with pytest.raises(FeatureExtractionError):
        fn(*args)


def test_rejects_nan_and_inf() -> None:
    with pytest.raises(FeatureExtractionError):
        split_speed_mps(float("nan"), 40.0)
    with pytest.raises(FeatureExtractionError):
        split_speed_mps(50.0, float("inf"))


def test_velocity_rejects_non_advancing_time() -> None:
    with pytest.raises(FeatureExtractionError):
        velocity_from_position_time(0.0, 10.0, 5.0, 5.0)
    with pytest.raises(FeatureExtractionError):
        velocity_from_position_time(0.0, 10.0, 5.0, 4.0)


def test_velocity_rejects_decreasing_distance() -> None:
    with pytest.raises(FeatureExtractionError):
        velocity_from_position_time(20.0, 10.0, 5.0, 8.0)


def test_split_ratios_rejects_zero_total() -> None:
    with pytest.raises(FeatureExtractionError):
        split_ratios([10.0], 0.0)


def test_rejects_bool_input() -> None:
    with pytest.raises(FeatureExtractionError):
        split_speed_mps(True, 40.0)  # type: ignore[arg-type]
