from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_timing_summary_keeps_duration_axes_separate() -> None:
    timing = report().timingSummary
    assert timing.wallDurationMs == 80_000
    assert timing.activeDurationMs == 80_000
    assert timing.stoppedDurationMs == 0
    assert timing.lifecyclePausedDurationMs == 0
    assert timing.elapsedDurationMs == timing.activeDurationMs + timing.stoppedDurationMs
