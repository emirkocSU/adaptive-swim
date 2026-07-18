"""SimClock: a manual, monotonic, bit-identical millisecond clock for deterministic tests.

Pure: no ``time.time()``, no ``datetime.now()``, no randomness, no I/O. It satisfies the
``contracts.events.Clock`` protocol (``now_ms``) and is advanced only by explicit calls, so
a given call sequence always produces identical timestamps.
"""

from __future__ import annotations

import math

from swimcore.time.errors import InvalidClockTimeError


def _check_time(value: int, name: str) -> None:
    """Reject non-finite, non-integer, or negative millisecond values.

    Times are integer milliseconds. ``bool`` is not accepted as an ``int`` here because a
    truth value is never a meaningful timestamp.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        # A float that happens to be non-finite must still be rejected clearly.
        if isinstance(value, float) and not math.isfinite(value):
            raise InvalidClockTimeError(f"{name} must be a finite integer, got {value!r}")
        raise InvalidClockTimeError(f"{name} must be an int (ms), got {type(value).__name__}")
    if value < 0:
        raise InvalidClockTimeError(f"{name} must be >= 0, got {value}")


class SimClock:
    """Manual monotonic clock. Advances only via :meth:`advance_ms`."""

    def __init__(self, start_ms: int = 0) -> None:
        _check_time(start_ms, "start_ms")
        self._now_ms = start_ms

    def now_ms(self) -> int:
        return self._now_ms

    def advance_ms(self, delta_ms: int) -> int:
        """Advance the clock forward by ``delta_ms`` (>= 0) and return the new time."""
        _check_time(delta_ms, "delta_ms")
        self._now_ms += delta_ms
        return self._now_ms

    def set_to(self, now_ms: int) -> int:
        """Jump the clock forward to ``now_ms``. Backward moves are rejected."""
        _check_time(now_ms, "now_ms")
        if now_ms < self._now_ms:
            raise InvalidClockTimeError(f"SimClock is monotonic: {now_ms} < current {self._now_ms}")
        self._now_ms = now_ms
        return self._now_ms
