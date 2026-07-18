"""Deterministic clock primitives: SimClock (manual monotonic) and ActiveClock.

``swimcore.time`` is pure: no wall-clock reads, no randomness, no I/O. Time enters the
domain only through these injected primitives.
"""

from __future__ import annotations

from swimcore.time.active_clock import ActiveClock, ActiveClockSnapshot
from swimcore.time.errors import (
    ClockAlreadyFrozenError,
    ClockAlreadyStartedError,
    ClockError,
    ClockNotFrozenError,
    ClockNotStartedError,
    InvalidClockTimeError,
    InvalidStopIntervalError,
)
from swimcore.time.sim_clock import SimClock

__all__ = [
    "ActiveClock",
    "ActiveClockSnapshot",
    "SimClock",
    "ClockError",
    "ClockAlreadyFrozenError",
    "ClockAlreadyStartedError",
    "ClockNotFrozenError",
    "ClockNotStartedError",
    "InvalidClockTimeError",
    "InvalidStopIntervalError",
]
