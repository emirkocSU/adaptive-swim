"""A10 negative-validation smoke: assert bad values are now rejected.

Run: ``python -m swimtools.negative_check`` (exit 0 = all bad values correctly rejected).
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from pydantic import ValidationError

from contracts.analytics import LengthOutcome, TrainingEfficiencyMetrics
from contracts.enums import (
    AdaptationMode,
    EventType,
    ExternalDataDomain,
    SplitQualityFlag,
    StopDetectionSource,
    StopPauseTrigger,
)
from contracts.events import EventEnvelope
from contracts.external_data import ExternalRecordProvenance, NormalizedSwimmingRecord
from contracts.stop_pause import StopPauseInterval
from contracts.workout import AdaptationPolicy


def _must_reject(label: str, fn: Callable[[], object]) -> bool:
    try:
        fn()
    except ValidationError:
        print(f"  OK  rejected: {label}")
        return True
    print(f"  FAIL not rejected: {label}")
    return False


def main() -> int:
    ok = True

    ok &= _must_reject(
        "slowestAllowedPaceSecPer100M = -5",
        lambda: AdaptationPolicy(mode=AdaptationMode.bounded_auto, slowestAllowedPaceSecPer100M=-5),
    )
    ok &= _must_reject(
        "startedAtMs = -100",
        lambda: StopPauseInterval(
            intervalId="i1",
            sessionId="s1",
            trigger=StopPauseTrigger.COACH_STOP,
            startedAtMs=-100,
            detectionSource=StopDetectionSource.COACH,
            createdBy="c",
        ),
    )
    ok &= _must_reject(
        "durationSec = -5",
        lambda: LengthOutcome(
            lengthIndex=0,
            targetTimeSec=80.0,
            stoppedDurationSec=-5.0,
            splitQualityFlag=SplitQualityFlag.RELIABLE,
        ),
    )
    ok &= _must_reject(
        "active=20, stopped=15, elapsed=999",
        lambda: LengthOutcome(
            lengthIndex=0,
            targetTimeSec=80.0,
            activeDurationSec=20.0,
            stoppedDurationSec=15.0,
            elapsedDurationSec=999.0,
            splitQualityFlag=SplitQualityFlag.RELIABLE,
        ),
    )
    ok &= _must_reject(
        "stopCount = -3",
        lambda: TrainingEfficiencyMetrics(
            activeSwimmingDurationSec=20.0,
            totalElapsedDurationSec=20.0,
            totalStoppedDurationSec=0.0,
            stopCount=-3,
            longestStopDurationSec=0.0,
            targetPaceDurationSec=18.0,
            targetPaceAdherenceRatio=0.9,
            highIntensityDurationSec=10.0,
            paceContinuityScore=0.8,
        ),
    )
    ok &= _must_reject(
        "performanceRelatedStopProbability = 4",
        lambda: TrainingEfficiencyMetrics(
            activeSwimmingDurationSec=20.0,
            totalElapsedDurationSec=20.0,
            totalStoppedDurationSec=0.0,
            stopCount=0,
            longestStopDurationSec=0.0,
            targetPaceDurationSec=18.0,
            targetPaceAdherenceRatio=0.9,
            highIntensityDurationSec=10.0,
            paceContinuityScore=0.8,
            performanceRelatedStopProbability=4.0,
        ),
    )
    ok &= _must_reject(
        "wrong EventType + wrong payload",
        lambda: EventEnvelope.model_validate(
            {
                "eventId": "e1",
                "seq": 1,
                "type": EventType.SplitRecorded,
                "tsMs": 1000,
                "producer": "edge",
                "payload": {
                    "intervalId": "i1",
                    "trigger": "MANUAL_INCIDENT",
                    "startedAtMs": 1000,
                    "detectionSource": "COACH",
                    "createdBy": "c",
                },
            }
        ),
    )
    ok &= _must_reject(
        "synthetic domain + synthetic=false",
        lambda: NormalizedSwimmingRecord(
            source_id="s1",
            source_record_id="r1",
            athlete_pseudonym="A#001",
            session_or_race_id="x1",
            data_domain=ExternalDataDomain.SYNTHETIC_SIMULATION,
            synthetic=False,
            provenance_ref=ExternalRecordProvenance(sourceId="s1", sourceRecordId="r1"),
        ),
    )

    print("negative-check:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
