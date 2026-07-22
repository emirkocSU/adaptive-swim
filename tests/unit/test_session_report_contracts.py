from __future__ import annotations

from contracts.analytics import (
    LengthOutcome,
    PacingMetrics,
    SessionReport,
    StopPauseSummary,
    TrainingEfficiencyMetrics,
)
from contracts.enums import SplitQualityFlag
from contracts.session_report import SessionReportV1_1
from tests.unit._analytics_helpers import report


def test_session_report_1_0_remains_parseable() -> None:
    old = SessionReport(
        sessionId="legacy",
        workoutRef="w1",
        pacingMetrics=PacingMetrics(
            meanAbsDeviationSec=0,
            deviationVariance=0,
            pacingConsistency=1,
            includedLengths=1,
            excludedLengths=0,
        ),
        trainingEfficiency=TrainingEfficiencyMetrics(
            activeSwimmingDurationSec=10,
            totalElapsedDurationSec=10,
            totalStoppedDurationSec=0,
            stopCount=0,
            longestStopDurationSec=0,
            targetPaceDurationSec=10,
            targetPaceAdherenceRatio=1,
            highIntensityDurationSec=0,
            paceContinuityScore=1,
        ),
        lengthOutcomes=[
            LengthOutcome(
                lengthIndex=0,
                targetTimeSec=10,
                activeDurationSec=10,
                elapsedDurationSec=10,
                splitQualityFlag=SplitQualityFlag.RELIABLE,
            )
        ],
        stopPauseSummary=StopPauseSummary(
            count=0,
            triggerDistribution={},
            totalStoppedDurationSec=0,
            longestStopDurationSec=0,
            affectedLengthIndices=[],
        ),
    )
    assert SessionReport.model_validate(old.model_dump()) == old


def test_session_report_1_1_contract_roundtrips() -> None:
    current = report()
    assert current.schemaVersion == "1.1"
    assert SessionReportV1_1.model_validate(current.model_dump()) == current
