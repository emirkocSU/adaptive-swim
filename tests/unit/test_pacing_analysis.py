from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_actual_and_target_pacing_shapes_are_separate() -> None:
    result = report((19_000, 38_000, 59_000, 82_000))
    assert result.pacingAnalysis.targetPacingShape.value == "EVEN"
    assert result.pacingAnalysis.actualPacingShape.value in {"POSITIVE_FADE", "IRREGULAR"}
