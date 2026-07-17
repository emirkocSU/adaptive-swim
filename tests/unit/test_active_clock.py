"""Commit 5 — ActiveClock: wall vs active time with retroactive StopPause freeze."""

from __future__ import annotations

import pytest

from swimcore.time import (
    ActiveClock,
    ClockAlreadyFrozenError,
    ClockAlreadyStartedError,
    ClockNotFrozenError,
    ClockNotStartedError,
    InvalidStopIntervalError,
)


def _started(at: int = 0) -> ActiveClock:
    c = ActiveClock()
    c.start(at)
    return c


def test_active_elapsed_before_pause() -> None:
    c = _started(0)
    assert c.active_elapsed_ms(8000) == 8000


def test_active_elapsed_requires_start() -> None:
    with pytest.raises(ClockNotStartedError):
        ActiveClock().active_elapsed_ms(1000)


def test_double_start_rejected() -> None:
    c = _started(0)
    with pytest.raises(ClockAlreadyStartedError):
        c.start(10)


def test_retroactive_freeze_from_real_stop_start() -> None:
    # start 0, stop begins 10000, confirmed 20000, queried at 20000
    c = _started(0)
    c.freeze_from(10000, 20000)
    snap = c.snapshot(20000)
    assert snap.activeElapsedMs == 10000
    assert snap.stoppedElapsedMs == 10000
    assert snap.wallElapsedMs == 20000


def test_active_time_stays_fixed_during_pause() -> None:
    c = _started(0)
    c.freeze_from(10000, 20000)
    assert c.active_elapsed_ms(20000) == 10000
    assert c.active_elapsed_ms(25000) == 10000  # still frozen


def test_resume_continues_active_time() -> None:
    c = _started(0)
    c.freeze_from(10000, 20000)
    c.resume(20000)
    # stopped interval [10000, 20000] = 10000 ms removed permanently
    assert c.active_elapsed_ms(25000) == 15000
    assert c.snapshot(25000).stoppedElapsedMs == 10000


def test_multiple_stop_pause_intervals() -> None:
    c = _started(0)
    c.freeze_from(5000, 6000)
    c.resume(8000)  # stopped 3000
    c.freeze_from(12000, 13000)
    c.resume(15000)  # stopped 3000 more → total 6000
    assert c.active_elapsed_ms(20000) == 20000 - 6000


def test_stop_start_before_clock_start_rejected() -> None:
    c = _started(1000)
    with pytest.raises(InvalidStopIntervalError):
        c.freeze_from(500, 2000)


def test_confirmation_before_stop_start_rejected() -> None:
    c = _started(0)
    with pytest.raises(InvalidStopIntervalError):
        c.freeze_from(10000, 9000)


def test_resume_before_stop_start_rejected() -> None:
    c = _started(0)
    c.freeze_from(10000, 20000)
    with pytest.raises(InvalidStopIntervalError):
        c.resume(9000)


def test_double_freeze_rejected() -> None:
    c = _started(0)
    c.freeze_from(10000, 20000)
    with pytest.raises(ClockAlreadyFrozenError):
        c.freeze_from(11000, 21000)


def test_resume_while_not_frozen_rejected() -> None:
    c = _started(0)
    with pytest.raises(ClockNotFrozenError):
        c.resume(1000)


# --------------------------------------------------------------------------- B6 additions
from swimcore.time import InvalidClockTimeError  # noqa: E402


def test_resume_before_confirmation_is_rejected() -> None:
    c = _started(0)
    c.freeze_from(10_000, 20_000)
    with pytest.raises(InvalidStopIntervalError):
        c.resume(15_000)  # before confirmation (20_000)


def test_snapshot_before_open_stop_start_is_rejected() -> None:
    c = _started(0)
    c.freeze_from(10_000, 20_000)  # lastTransition = 20_000
    with pytest.raises(InvalidClockTimeError):
        c.snapshot(9_000)


def test_snapshot_before_last_transition_is_rejected() -> None:
    c = _started(0)
    c.freeze_from(10_000, 20_000)
    c.resume(20_000)  # lastTransition = 20_000
    with pytest.raises(InvalidClockTimeError):
        c.snapshot(15_000)
    with pytest.raises(InvalidClockTimeError):
        c.active_elapsed_ms(0)


def test_active_elapsed_never_exceeds_wall_during_freeze() -> None:
    c = _started(0)
    c.freeze_from(10_000, 20_000)
    for now in (20_000, 25_000, 40_000):
        snap = c.snapshot(now)
        assert 0 <= snap.activeElapsedMs <= snap.wallElapsedMs


def test_stopped_elapsed_never_becomes_negative() -> None:
    c = _started(0)
    c.freeze_from(5_000, 6_000)
    c.resume(9_000)
    for now in (9_000, 12_000, 30_000):
        assert c.snapshot(now).stoppedElapsedMs >= 0


def test_active_elapsed_never_decreases_across_transitions() -> None:
    c = _started(0)
    a1 = c.active_elapsed_ms(5_000)
    c.freeze_from(6_000, 8_000)
    a2 = c.active_elapsed_ms(8_000)
    c.resume(8_000)
    a3 = c.active_elapsed_ms(8_000)
    a4 = c.active_elapsed_ms(12_000)
    assert a1 <= a2 <= a3 <= a4


def test_wall_equals_active_plus_stopped() -> None:
    c = _started(0)
    c.freeze_from(10_000, 20_000)
    c.resume(25_000)
    snap = c.snapshot(30_000)
    assert snap.wallElapsedMs == snap.activeElapsedMs + snap.stoppedElapsedMs


def test_second_stop_after_resume_is_supported() -> None:
    c = _started(0)
    c.freeze_from(5_000, 6_000)
    c.resume(8_000)  # stopped 3_000
    c.freeze_from(12_000, 13_000)
    c.resume(16_000)  # stopped 4_000 → total 7_000
    assert c.active_elapsed_ms(20_000) == 20_000 - 7_000


# --------------------------------------------------------------------------- forward-only (fix 1)
def test_snapshot_cannot_move_backward_without_transition() -> None:
    c = _started(0)
    c.snapshot(100_000)
    with pytest.raises(InvalidClockTimeError):
        c.snapshot(50_000)  # active time must not fall from 100 s back to 50 s


def test_freeze_confirmation_cannot_precede_last_observed_time() -> None:
    c = _started(0)
    c.snapshot(100_000)  # observed 100 s
    with pytest.raises(InvalidClockTimeError):
        c.freeze_from(50_000, 60_000)  # cannot confirm a stop at 60 s in the past


def test_active_elapsed_query_advances_forward_watermark() -> None:
    c = _started(0)
    c.active_elapsed_ms(80_000)
    with pytest.raises(InvalidClockTimeError):
        c.active_elapsed_ms(40_000)
