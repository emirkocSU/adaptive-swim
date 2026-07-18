"""ActiveClock: monotonic runtime primitive separating wall vs active swimming time.

    active elapsed = wall elapsed - confirmed stopped intervals

This is a **forward-only runtime clock**, not an event store: it does not answer historical
queries. Any snapshot/query time earlier than the last transition is rejected. Historical
replay is reconstructed from events in a later commit.

A StopPause is confirmed retroactively: if a stop *began* at 10000 ms but was *confirmed* at
20000 ms (10 s threshold), the freeze start is the real 10000 ms and, queried at 20000 ms,
``active = 10000`` / ``stopped = 10000`` / ``wall = 20000``. Resume may not precede the
confirmation time. It applies externally confirmed StopPauses; it never detects one.
"""

from __future__ import annotations

from dataclasses import dataclass

from swimcore.time.errors import (
    ClockAlreadyFrozenError,
    ClockAlreadyStartedError,
    ClockNotFrozenError,
    ClockNotStartedError,
    InvalidClockTimeError,
    InvalidStopIntervalError,
)
from swimcore.time.sim_clock import _check_time


@dataclass(frozen=True, slots=True)
class ActiveClockSnapshot:
    startedAtMs: int
    lastTransitionAtMs: int
    wallElapsedMs: int
    activeElapsedMs: int
    stoppedElapsedMs: int
    frozen: bool


class ActiveClock:
    def __init__(self) -> None:
        self._started_at_ms: int | None = None
        self._last_transition_at_ms: int = 0
        #: High-water mark of every observed time (transitions *and* queries). The clock is
        #: strictly forward-only: nothing may be observed earlier than this.
        self._last_observed_at_ms: int = 0
        self._completed_stopped_ms: int = 0
        self._open_stop_started_at_ms: int | None = None
        self._open_stop_confirmed_at_ms: int | None = None
        #: Resume time of the most recent completed StopPause; a new stop may not start before it.
        self._last_completed_stop_resumed_at_ms: int = 0

    # ------------------------------------------------------------------ accessors
    @property
    def started_at_ms(self) -> int:
        if self._started_at_ms is None:
            raise ClockNotStartedError("clock not started")
        return self._started_at_ms

    @property
    def last_transition_at_ms(self) -> int:
        return self._last_transition_at_ms

    @property
    def last_observed_at_ms(self) -> int:
        return self._last_observed_at_ms

    @property
    def is_frozen(self) -> bool:
        return self._open_stop_started_at_ms is not None

    # ------------------------------------------------------------------ transitions
    def start(self, started_at_ms: int) -> None:
        if self._started_at_ms is not None:
            raise ClockAlreadyStartedError("clock already started")
        _check_time(started_at_ms, "started_at_ms")
        self._started_at_ms = started_at_ms
        self._last_transition_at_ms = started_at_ms
        self._last_observed_at_ms = started_at_ms

    def freeze_from(self, stop_started_at_ms: int, confirmed_at_ms: int) -> None:
        start = self.started_at_ms
        _check_time(stop_started_at_ms, "stop_started_at_ms")
        _check_time(confirmed_at_ms, "confirmed_at_ms")
        if self.is_frozen:
            raise ClockAlreadyFrozenError("an open StopPause already exists")
        if stop_started_at_ms < start:
            raise InvalidStopIntervalError(
                f"stop start {stop_started_at_ms} before clock start {start}"
            )
        if stop_started_at_ms < self._last_completed_stop_resumed_at_ms:
            raise InvalidStopIntervalError(
                f"stop start {stop_started_at_ms} overlaps the previous StopPause resumed at "
                f"{self._last_completed_stop_resumed_at_ms}"
            )
        if confirmed_at_ms < stop_started_at_ms:
            raise InvalidStopIntervalError(
                f"confirmation {confirmed_at_ms} precedes stop start {stop_started_at_ms}"
            )
        # Forward-only: the *confirmation* may not precede the last observed time. The
        # retroactive stop *start* is intentionally NOT compared, so a stop that began at
        # 10 s can still be confirmed at 20 s — but a confirmation at 60 s is rejected once
        # 100 s has already been observed.
        if confirmed_at_ms < self._last_observed_at_ms:
            raise InvalidClockTimeError(
                f"confirmation {confirmed_at_ms} precedes last observed time "
                f"{self._last_observed_at_ms}; ActiveClock is forward-only"
            )
        self._open_stop_started_at_ms = stop_started_at_ms
        self._open_stop_confirmed_at_ms = confirmed_at_ms
        self._last_transition_at_ms = confirmed_at_ms
        self._last_observed_at_ms = confirmed_at_ms

    def resume(self, resumed_at_ms: int) -> None:
        if not self.is_frozen:
            raise ClockNotFrozenError("no open StopPause to resume")
        assert self._open_stop_started_at_ms is not None
        assert self._open_stop_confirmed_at_ms is not None
        _check_time(resumed_at_ms, "resumed_at_ms")
        if resumed_at_ms < self._open_stop_confirmed_at_ms:
            raise InvalidStopIntervalError(
                f"resume {resumed_at_ms} precedes confirmation {self._open_stop_confirmed_at_ms}"
            )
        if resumed_at_ms < self._last_observed_at_ms:
            raise InvalidClockTimeError(
                f"resume {resumed_at_ms} precedes last observed time "
                f"{self._last_observed_at_ms}; ActiveClock is forward-only"
            )
        self._completed_stopped_ms += resumed_at_ms - self._open_stop_started_at_ms
        self._open_stop_started_at_ms = None
        self._open_stop_confirmed_at_ms = None
        self._last_transition_at_ms = resumed_at_ms
        self._last_observed_at_ms = resumed_at_ms
        self._last_completed_stop_resumed_at_ms = resumed_at_ms

    # ------------------------------------------------------------------ queries
    def _observe(self, now_ms: int) -> None:
        _check_time(now_ms, "now_ms")
        if now_ms < self._last_observed_at_ms:
            raise InvalidClockTimeError(
                f"now {now_ms} is before the last observed time "
                f"{self._last_observed_at_ms}; ActiveClock is forward-only"
            )
        self._last_observed_at_ms = now_ms

    def active_elapsed_ms(self, now_ms: int) -> int:
        start = self.started_at_ms
        self._observe(now_ms)
        if self._open_stop_started_at_ms is not None:
            # frozen: active pinned to its value at the real stop start
            return (self._open_stop_started_at_ms - start) - self._completed_stopped_ms
        return (now_ms - start) - self._completed_stopped_ms

    def snapshot(self, now_ms: int) -> ActiveClockSnapshot:
        start = self.started_at_ms
        active = self.active_elapsed_ms(now_ms)
        wall = now_ms - start
        return ActiveClockSnapshot(
            startedAtMs=start,
            lastTransitionAtMs=self._last_transition_at_ms,
            wallElapsedMs=wall,
            activeElapsedMs=active,
            stoppedElapsedMs=wall - active,
            frozen=self.is_frozen,
        )
