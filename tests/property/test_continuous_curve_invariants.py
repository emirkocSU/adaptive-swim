"""Property-based continuous curve invariants (Commit 8 §39)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from swimcore.pacing.continuous_profile_compiler import (
    CURVE_TIME_TOLERANCE_SEC,
    compile_continuous_pace_profile,
)
from swimcore.pacing.timeline import (
    ghost_distance_at_active_time,
    target_active_time_at_distance,
)
from tests.unit._continuous_helpers import knots, pchip_profile

pytestmark = pytest.mark.property

_speeds = st.floats(min_value=0.8, max_value=2.2, allow_nan=False, allow_infinity=False)


@st.composite
def _profiles(draw: st.DrawFn):  # noqa: ANN202
    total = draw(st.sampled_from([100.0, 200.0]))
    target = draw(st.floats(min_value=60.0, max_value=200.0))
    mid = total / 2.0
    s0 = draw(_speeds)
    s1 = draw(_speeds)
    s2 = draw(_speeds)
    return pchip_profile(
        total=total,
        target_time=target,
        curve_knots=knots((0.0, s0), (mid, s1), (total, s2)),
    )


def _compile(profile):  # noqa: ANN001, ANN202
    return compile_continuous_pace_profile(
        profile,
        pool_length_m=profile.poolLengthM,
        resolved_start_mode=profile.startMode,
        stroke=profile.stroke,
        total_distance_m=profile.totalDistanceM,
    )


@given(_profiles())
@settings(max_examples=60, deadline=None)
def test_compile_twice_equal_timeline(profile) -> None:  # noqa: ANN001
    a = _compile(profile)
    b = _compile(profile)
    assert a.timeline == b.timeline


@given(_profiles())
@settings(max_examples=60, deadline=None)
def test_target_total_exact(profile) -> None:  # noqa: ANN001
    plan = _compile(profile)
    target = profile.targetTimeConstraint.targetTotalTimeSec
    assert abs(plan.timeline.totalActiveDurationSec - target) <= max(CURVE_TIME_TOLERANCE_SEC, 1e-6)


@given(_profiles())
@settings(max_examples=60, deadline=None)
def test_speeds_finite_and_positive(profile) -> None:  # noqa: ANN001
    s = _compile(profile).validationSummary
    assert s.minTargetSpeedMps > 0.0
    assert s.maxTargetSpeedMps >= s.minTargetSpeedMps


@given(_profiles())
@settings(max_examples=40, deadline=None)
def test_distance_time_roundtrip(profile) -> None:  # noqa: ANN001
    plan = _compile(profile)
    total = profile.totalDistanceM
    for frac in (0.2, 0.5, 0.8):
        d = total * frac
        t = target_active_time_at_distance(plan.timeline, d).elapsedActiveSec
        back = ghost_distance_at_active_time(plan.timeline, t).distanceM
        assert abs(back - d) < 5e-2


@given(_profiles())
@settings(max_examples=40, deadline=None)
def test_input_profile_never_mutated(profile) -> None:  # noqa: ANN001
    before = profile.model_dump(mode="json")
    _compile(profile)
    assert profile.model_dump(mode="json") == before
