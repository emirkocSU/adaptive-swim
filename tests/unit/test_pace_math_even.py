"""Commit 4 — even pace formulas and constant-pace round trips."""

from __future__ import annotations

import math

import pytest

from swimcore.pacing import (
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceError,
    distance_for_duration,
    duration_for_distance,
)
from swimcore.pacing.types import EPSILON


def test_even_pace_exact_duration() -> None:
    assert duration_for_distance(100, 80) == pytest.approx(80.0)
    assert duration_for_distance(50, 80) == pytest.approx(40.0)
    assert duration_for_distance(25, 72) == pytest.approx(18.0)


def test_zero_distance_is_zero_duration() -> None:
    assert duration_for_distance(0, 80) == 0.0


def test_zero_duration_is_zero_distance() -> None:
    assert distance_for_duration(0, 80) == 0.0


def test_negative_distance_rejected() -> None:
    with pytest.raises(InvalidDistanceError):
        duration_for_distance(-10, 80)


def test_negative_duration_rejected() -> None:
    with pytest.raises(InvalidDurationError):
        distance_for_duration(-10, 80)


def test_invalid_pace_rejected() -> None:
    with pytest.raises(InvalidPaceError):
        duration_for_distance(100, 0)
    with pytest.raises(InvalidPaceError):
        duration_for_distance(100, -5)


def test_nan_and_infinity_rejected() -> None:
    with pytest.raises(InvalidDistanceError):
        duration_for_distance(math.nan, 80)
    with pytest.raises(InvalidPaceError):
        duration_for_distance(100, math.inf)


def test_distance_time_distance_round_trip() -> None:
    for d, p in ((100, 80), (37.5, 72.3), (400, 95.1)):
        t = duration_for_distance(d, p)
        back = distance_for_duration(t, p)
        assert abs(back - d) < 1e-9 + EPSILON
