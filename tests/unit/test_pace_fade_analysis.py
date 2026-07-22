from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_pace_fade_and_decline_are_deterministic() -> None:
    result = report((18_000, 37_000, 59_000, 84_000))
    fade = result.pacingAnalysis.fade
    assert fade.actualPaceFadePct is not None
    assert fade.actualPaceFadePct < 0
    assert fade.paceDeclineSlope is not None
