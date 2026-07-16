"""Commit 2 numeric / cross-field / typed-payload constraint tests (A9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts.analytics import (
    LengthOutcome,
    StopPauseSummary,
    TrainingEfficiencyMetrics,
)
from contracts.enums import (
    EventType,
    SplitQualityFlag,
    StopDetectionSource,
    StopPauseTrigger,
)
from contracts.events import EventEnvelope, StopPauseStartedPayload
from contracts.stop_pause import StopPauseInterval, StopPausePolicy
from contracts.workout import WorkoutTemplateVersion

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "src" / "contracts" / "schemas"


# --------------------------------------------------------------------------- factories
def _valid_workout(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "schemaVersion": "1.0",
        "name": "T",
        "poolLengthM": 25,
        "stroke": "freestyle",
        "blocks": [
            {
                "type": "repeat",
                "repetitions": 1,
                "distanceM": 100,
                "rest": {"type": "none"},
                "segments": [
                    {"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 83.0}
                ],
            }
        ],
    }
    doc.update(overrides)
    return doc


def _training_efficiency(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "activeSwimmingDurationSec": 20.0,
        "totalElapsedDurationSec": 35.0,
        "totalStoppedDurationSec": 15.0,
        "stopCount": 1,
        "longestStopDurationSec": 15.0,
        "targetPaceDurationSec": 18.0,
        "targetPaceAdherenceRatio": 0.9,
        "highIntensityDurationSec": 10.0,
        "paceContinuityScore": 0.8,
    }
    doc.update(overrides)
    return doc


def _stop_interval(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "intervalId": "i1",
        "sessionId": "s1",
        "trigger": StopPauseTrigger.COACH_STOP,
        "startedAtMs": 1000,
        "detectionSource": StopDetectionSource.COACH,
        "createdBy": "coach1",
    }
    doc.update(overrides)
    return doc


def _envelope(
    payload_type: EventType, payload: dict[str, object], **ov: object
) -> dict[str, object]:
    doc: dict[str, object] = {
        "eventId": "e1",
        "seq": 1,
        "type": payload_type,
        "tsMs": 1000,
        "producer": "edge",
        "payload": payload,
    }
    doc.update(ov)
    return doc


# --------------------------------------------------------------------------- schema version
def test_schema_version_is_required() -> None:
    doc = _valid_workout()
    del doc["schemaVersion"]
    with pytest.raises(ValidationError):
        WorkoutTemplateVersion(**doc)


def test_schema_version_present_in_generated_schema() -> None:
    schema = json.loads((SCHEMA_DIR / "workout-1.0.json").read_text(encoding="utf-8"))
    assert "schemaVersion" in schema["required"]
    assert schema["properties"]["schemaVersion"].get("const") == "1.0"


# --------------------------------------------------------------------------- numeric guards
def test_negative_pace_is_rejected() -> None:
    doc = _valid_workout()
    doc["blocks"][0]["segments"][0]["targetPaceSecPer100M"] = -5  # type: ignore[index]
    with pytest.raises(ValidationError):
        WorkoutTemplateVersion(**doc)


def test_negative_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StopPauseInterval(**_stop_interval(startedAtMs=-100))


def test_negative_duration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LengthOutcome(
            lengthIndex=0,
            targetTimeSec=80.0,
            activeDurationSec=-5.0,
            splitQualityFlag=SplitQualityFlag.RELIABLE,
        )


def test_negative_index_and_count_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StopPauseInterval(**_stop_interval(relatedSetIndex=-1))
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(**_training_efficiency(stopCount=-3))


def test_probability_outside_zero_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(**_training_efficiency(performanceRelatedStopProbability=4.0))


def test_ratio_outside_zero_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(**_training_efficiency(targetPaceAdherenceRatio=1.5))


# --------------------------------------------------------------------------- stop time relations
def test_stop_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StopPauseInterval(**_stop_interval(startedAtMs=5000, endedAtMs=1000, durationSec=-4.0))


def test_resolved_stop_requires_duration() -> None:
    with pytest.raises(ValidationError):
        StopPauseInterval(**_stop_interval(startedAtMs=1000, endedAtMs=6000))


def test_stop_duration_matches_timestamps() -> None:
    # correct: (6000 - 1000)/1000 = 5.0
    StopPauseInterval(**_stop_interval(startedAtMs=1000, endedAtMs=6000, durationSec=5.0))
    with pytest.raises(ValidationError):
        StopPauseInterval(**_stop_interval(startedAtMs=1000, endedAtMs=6000, durationSec=99.0))


# --------------------------------------------------------------------------- duration accounting
def test_length_duration_accounting() -> None:
    LengthOutcome(
        lengthIndex=0,
        targetTimeSec=80.0,
        activeDurationSec=20.0,
        stoppedDurationSec=15.0,
        elapsedDurationSec=35.0,
        splitQualityFlag=SplitQualityFlag.RELIABLE,
    )
    with pytest.raises(ValidationError):
        LengthOutcome(
            lengthIndex=0,
            targetTimeSec=80.0,
            activeDurationSec=20.0,
            stoppedDurationSec=15.0,
            elapsedDurationSec=999.0,
            splitQualityFlag=SplitQualityFlag.RELIABLE,
        )


def test_session_duration_accounting() -> None:
    TrainingEfficiencyMetrics(**_training_efficiency())
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(**_training_efficiency(totalElapsedDurationSec=999.0))


def test_longest_stop_not_greater_than_total_stop() -> None:
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(**_training_efficiency(longestStopDurationSec=99.0))
    with pytest.raises(ValidationError):
        StopPauseSummary(
            count=1,
            triggerDistribution={StopPauseTrigger.COACH_STOP: 1},
            totalStoppedDurationSec=10.0,
            longestStopDurationSec=20.0,
            affectedLengthIndices=[3],
        )


def test_zero_stop_count_requires_zero_stop_duration() -> None:
    TrainingEfficiencyMetrics(
        **_training_efficiency(
            stopCount=0,
            totalStoppedDurationSec=0.0,
            longestStopDurationSec=0.0,
            totalElapsedDurationSec=20.0,
        )
    )
    with pytest.raises(ValidationError):
        TrainingEfficiencyMetrics(
            **_training_efficiency(
                stopCount=0,
                totalStoppedDurationSec=15.0,
                longestStopDurationSec=15.0,
            )
        )


# --------------------------------------------------------------------------- typed events
def test_event_payload_is_typed() -> None:
    env = EventEnvelope(
        **_envelope(
            EventType.StopPauseStarted,
            {
                "intervalId": "i1",
                "trigger": "MANUAL_INCIDENT",
                "startedAtMs": 1000,
                "detectionSource": "COACH",
                "createdBy": "coach1",
            },
        )
    )
    assert isinstance(env.payload, StopPauseStartedPayload)


def test_event_type_payload_mismatch_is_rejected() -> None:
    # A SplitRecorded event carrying a StopPause-shaped payload must be rejected.
    with pytest.raises(ValidationError):
        EventEnvelope(
            **_envelope(
                EventType.SplitRecorded,
                {
                    "intervalId": "i1",
                    "trigger": "MANUAL_INCIDENT",
                    "startedAtMs": 1000,
                    "detectionSource": "COACH",
                    "createdBy": "coach1",
                },
            )
        )


def test_stop_pause_started_requires_expected_payload() -> None:
    # Missing required StopPause fields (intervalId, createdBy, ...) → rejected.
    with pytest.raises(ValidationError):
        EventEnvelope(**_envelope(EventType.StopPauseStarted, {"trigger": "COACH_STOP"}))


# --------------------------------------------------------------------------- stop pause policy
def test_stop_pause_policy_threshold_is_positive() -> None:
    with pytest.raises(ValidationError):
        StopPausePolicy(longStopThresholdSec=0)
    with pytest.raises(ValidationError):
        StopPausePolicy(longStopThresholdSec=-5)


def test_stop_pause_policy_is_configurable() -> None:
    default = StopPausePolicy()
    assert default.longStopThresholdSec == 10.0  # default hypothesis, not a fixed core value
    custom = StopPausePolicy(longStopThresholdSec=7.5, automaticDetectionEnabled=True)
    assert custom.longStopThresholdSec == 7.5
    assert custom.automaticDetectionEnabled is True


# --------------------------------------------------------------------------- synthetic data
def _record(domain: str, synthetic: bool) -> object:
    from contracts.enums import ExternalDataDomain
    from contracts.external_data import ExternalRecordProvenance, NormalizedSwimmingRecord

    return NormalizedSwimmingRecord(
        source_id="s1",
        source_record_id="r1",
        athlete_pseudonym="A#001",
        session_or_race_id="x1",
        data_domain=ExternalDataDomain(domain),
        synthetic=synthetic,
        provenance_ref=ExternalRecordProvenance(sourceId="s1", sourceRecordId="r1"),
    )


def test_synthetic_domain_requires_synthetic_true() -> None:
    with pytest.raises(ValidationError):
        _record("SYNTHETIC_SIMULATION", synthetic=False)
    _record("SYNTHETIC_SIMULATION", synthetic=True)  # valid


def test_real_domain_rejects_synthetic_true() -> None:
    with pytest.raises(ValidationError):
        _record("ELITE_RACE", synthetic=True)
    _record("ELITE_RACE", synthetic=False)  # valid


def test_synthetic_record_requires_provenance() -> None:
    from contracts.enums import ExternalDataDomain
    from contracts.external_data import ExternalRecordProvenance, NormalizedSwimmingRecord

    # empty provenance id on a synthetic record → rejected
    with pytest.raises(ValidationError):
        NormalizedSwimmingRecord(
            source_id="s1",
            source_record_id="r1",
            athlete_pseudonym="A#001",
            session_or_race_id="x1",
            data_domain=ExternalDataDomain.SYNTHETIC_SIMULATION,
            synthetic=True,
            provenance_ref=ExternalRecordProvenance(sourceId="", sourceRecordId="r1"),
        )
