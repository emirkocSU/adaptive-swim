"""Continuous pace-profile 1.1 contract tests (Commit 8 §35)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts.continuous_pace import (
    ApprovedContinuousPaceProfile,
    ContinuousPaceCurve,
    ContinuousPacePhase,
    CurveProvenance,
    PaceCurveKnot,
    SplitTimeConstraint,
    TargetTimeConstraint,
)
from contracts.enums import (
    ContinuousCurveGenerationMode,
    ContinuousPacePhaseType,
    PaceCurveRepresentation,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    TargetTimeSource,
    WorkoutGoal,
)

_FIXTURES = (
    Path(__file__).resolve().parents[2] / "src" / "contracts" / "examples" / "valid_v1_1_continuous"
)


def _knots(*pairs: tuple[float, float]) -> tuple[PaceCurveKnot, ...]:
    return tuple(
        PaceCurveKnot(knotIndex=i, distanceM=d, targetSpeedMps=s) for i, (d, s) in enumerate(pairs)
    )


def _profile(**overrides: object) -> ApprovedContinuousPaceProfile:
    base: dict[str, object] = {
        "profileId": "p",
        "profileVersion": "1",
        "source": PaceProfileSource.COACH_AUTHORED,
        "profileType": PaceProfileType.EVEN_PACE,
        "approvalStatus": ProfileApprovalStatus.COACH_APPROVED,
        "poolLengthM": 25,
        "startMode": StartMode.DIVE_START,
        "stroke": Stroke.freestyle,
        "workoutGoal": WorkoutGoal.RACE_PACE,
        "totalDistanceM": 100.0,
        "targetTimeConstraint": TargetTimeConstraint(
            targetTotalTimeSec=80.0, source=TargetTimeSource.COACH
        ),
        "curve": ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=_knots((0.0, 1.25), (100.0, 1.25)),
        ),
        "phases": (
            ContinuousPacePhase(
                phaseIndex=0, fromM=0.0, toM=100.0, phaseType=ContinuousPacePhaseType.SURFACE_SWIM
            ),
        ),
        "curveProvenance": CurveProvenance(
            generationMode=ContinuousCurveGenerationMode.MANUAL_CONTINUOUS_PROFILE,
            targetTimeSource=TargetTimeSource.COACH,
        ),
    }
    base.update(overrides)
    return ApprovedContinuousPaceProfile(**base)  # type: ignore[arg-type]


def test_valid_profile_builds() -> None:
    p = _profile()
    assert p.schemaVersion == "1.1"
    assert p.totalDistanceM == 100.0
    assert p.is_live_eligible


def test_schema_version_is_literal_1_1() -> None:
    with pytest.raises(ValidationError):
        _profile(schemaVersion="1.0")


def test_first_knot_must_be_zero() -> None:
    with pytest.raises(ValidationError, match="first knot must be at 0"):
        _profile(
            curve=ContinuousPaceCurve(
                representation=PaceCurveRepresentation.PCHIP,
                knots=_knots((5.0, 1.25), (100.0, 1.25)),
            )
        )


def test_last_knot_must_reach_total() -> None:
    with pytest.raises(ValidationError, match="curve covers"):
        _profile(
            curve=ContinuousPaceCurve(
                representation=PaceCurveRepresentation.PCHIP,
                knots=_knots((0.0, 1.25), (90.0, 1.25)),
            )
        )


def test_strictly_increasing_knot_distance() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=_knots((0.0, 1.2), (50.0, 1.2), (50.0, 1.2)),
        )


def test_duplicate_knot_rejected() -> None:
    with pytest.raises(ValidationError):
        ContinuousPaceCurve(
            representation=PaceCurveRepresentation.PCHIP,
            knots=_knots((0.0, 1.2), (50.0, 1.2), (50.0, 1.3), (100.0, 1.2)),
        )


def test_zero_speed_rejected() -> None:
    with pytest.raises(ValidationError):
        PaceCurveKnot(knotIndex=0, distanceM=0.0, targetSpeedMps=0.0)


def test_negative_speed_rejected() -> None:
    with pytest.raises(ValidationError):
        PaceCurveKnot(knotIndex=0, distanceM=0.0, targetSpeedMps=-1.0)


def test_phase_coverage_must_be_contiguous() -> None:
    with pytest.raises(ValidationError, match="gap/overlap"):
        _profile(
            phases=(
                ContinuousPacePhase(
                    phaseIndex=0,
                    fromM=0.0,
                    toM=40.0,
                    phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
                ),
                ContinuousPacePhase(
                    phaseIndex=1, fromM=50.0, toM=100.0, phaseType=ContinuousPacePhaseType.FINISH
                ),
            )
        )


def test_phase_overlap_rejected() -> None:
    with pytest.raises(ValidationError, match="gap/overlap"):
        _profile(
            phases=(
                ContinuousPacePhase(
                    phaseIndex=0,
                    fromM=0.0,
                    toM=60.0,
                    phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
                ),
                ContinuousPacePhase(
                    phaseIndex=1, fromM=50.0, toM=100.0, phaseType=ContinuousPacePhaseType.FINISH
                ),
            )
        )


def test_phase_must_end_at_total() -> None:
    with pytest.raises(ValidationError, match="last phase must end"):
        _profile(
            phases=(
                ContinuousPacePhase(
                    phaseIndex=0,
                    fromM=0.0,
                    toM=90.0,
                    phaseType=ContinuousPacePhaseType.SURFACE_SWIM,
                ),
            )
        )


def test_locked_split_sum_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match="locked split durations sum"):
        _profile(
            splitTimeConstraints=(
                SplitTimeConstraint(
                    splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=30.0, lockedByCoach=True
                ),
                SplitTimeConstraint(
                    splitIndex=1, fromM=50.0, toM=100.0, targetDurationSec=30.0, lockedByCoach=True
                ),
            )
        )


def test_locked_split_exceeding_total_rejected() -> None:
    with pytest.raises(ValidationError, match="exceed target total"):
        _profile(
            splitTimeConstraints=(
                SplitTimeConstraint(
                    splitIndex=0, fromM=0.0, toM=50.0, targetDurationSec=90.0, lockedByCoach=True
                ),
            )
        )


def test_split_boundary_must_be_pool_aligned() -> None:
    with pytest.raises(ValidationError, match="wall multiple"):
        _profile(
            splitTimeConstraints=(
                SplitTimeConstraint(
                    splitIndex=0, fromM=0.0, toM=30.0, targetDurationSec=24.0, lockedByCoach=True
                ),
            )
        )


def test_pool_must_be_25_or_50() -> None:
    with pytest.raises(ValidationError, match="poolLengthM must be 25 or 50"):
        _profile(poolLengthM=33)


def test_extra_fields_rejected() -> None:
    data = _profile().model_dump(mode="json")
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        ApprovedContinuousPaceProfile.model_validate(data)


def test_coach_lock_requires_eligible_status() -> None:
    with pytest.raises(ValidationError, match="live-eligible"):
        _profile(coachLocked=True, approvalStatus=ProfileApprovalStatus.DRAFT)


def test_constant_speed_requires_contiguous_segments() -> None:
    from contracts.continuous_pace import ConstantSpeedCurveSegment

    with pytest.raises(ValidationError, match="gap/overlap"):
        ContinuousPaceCurve(
            representation=PaceCurveRepresentation.CONSTANT_SPEED,
            segments=(
                ConstantSpeedCurveSegment(segmentIndex=0, fromM=0.0, toM=50.0, targetSpeedMps=1.2),
                ConstantSpeedCurveSegment(
                    segmentIndex=1, fromM=60.0, toM=100.0, targetSpeedMps=1.2
                ),
            ),
        )


@pytest.mark.parametrize(
    "name",
    [
        "fixture1_200m_25m_dive_133s_pchip_locked",
        "fixture2_200m_25m_dive_133s_alt_microcurve",
        "fixture3_200m_50m_independent",
        "fixture4_800m_negative_progressive",
        "fixture5_migrated_legacy_1_0",
    ],
)
def test_valid_fixtures_load(name: str) -> None:
    data = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    profile = ApprovedContinuousPaceProfile(**data)
    assert profile.schemaVersion == "1.1"
    assert profile.is_live_eligible


def test_migration_provenance_present_in_fixture5() -> None:
    data = json.loads((_FIXTURES / "fixture5_migrated_legacy_1_0.json").read_text(encoding="utf-8"))
    profile = ApprovedContinuousPaceProfile(**data)
    assert profile.curveProvenance.migratedFromSchemaVersion == "1.0"
    assert profile.curveProvenance.migrationVersion is not None
    assert profile.curveProvenance.legacyProfileId is not None
    assert profile.curve.representation is PaceCurveRepresentation.CONSTANT_SPEED


_INVALID = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "contracts"
    / "examples"
    / "invalid_v1_1_continuous"
)


@pytest.mark.parametrize(
    "name",
    [
        "invalid_duplicate_knot",
        "invalid_first_knot_offset",
        "invalid_last_knot_mismatch",
        "invalid_zero_speed",
        "invalid_negative_speed",
        "invalid_phase_gap",
        "invalid_phase_overlap",
        "invalid_locked_split_sum",
        "invalid_total_mismatch",
        "invalid_pool",
        "invalid_split_not_wall_aligned",
        "invalid_locked_exceeds_total",
    ],
)
def test_invalid_fixtures_rejected(name: str) -> None:
    data = json.loads((_INVALID / f"{name}.json").read_text(encoding="utf-8"))
    with pytest.raises((ValidationError, ValueError)):
        ApprovedContinuousPaceProfile(**data)
