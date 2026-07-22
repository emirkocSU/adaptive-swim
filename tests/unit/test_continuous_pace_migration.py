"""1.0 -> 1.1 migration tests, incl. bit-identical timeline (Demonstration B, §36)."""

from __future__ import annotations

import pytest

from contracts.enums import (
    PaceProfilePhase,
    PaceProfileSource,
    PaceProfileType,
    ProfileApprovalStatus,
    StartMode,
    Stroke,
    WorkoutGoal,
)
from contracts.pace_profiles import ApprovedPaceProfile, PaceProfileLeg
from swimcore.pacing.continuous_migration import (
    MIGRATION_VERSION,
    migrate_approved_pace_profile_1_0_to_1_1,
)
from swimcore.pacing.continuous_profile_compiler import compile_continuous_pace_profile
from swimcore.pacing.profile_compiler import compile_approved_pace_profile
from swimcore.pacing.timeline import target_active_time_at_distance


def _legacy(pool: int = 25) -> ApprovedPaceProfile:
    return ApprovedPaceProfile(
        profileId="legacy1",
        profileVersion="1",
        source=PaceProfileSource.LEGACY_SEGMENTS,
        profileType=PaceProfileType.NEGATIVE_SPLIT,
        approvalStatus=ProfileApprovalStatus.COACH_APPROVED,
        poolLengthM=pool,
        startMode=StartMode.DIVE_START,
        stroke=Stroke.freestyle,
        workoutGoal=WorkoutGoal.RACE_PACE,
        targetTotalTimeSec=82.0,
        legs=[
            PaceProfileLeg(
                legIndex=0,
                fromM=0.0,
                toM=50.0,
                targetDurationSec=40.0,
                phaseType=PaceProfilePhase.SURFACE_SWIM,
            ),
            PaceProfileLeg(
                legIndex=1,
                fromM=50.0,
                toM=100.0,
                targetDurationSec=42.0,
                phaseType=PaceProfilePhase.FINISH,
            ),
        ],
    )


def _compile_1_0(profile: ApprovedPaceProfile):  # noqa: ANN202
    return compile_approved_pace_profile(
        profile,
        pool_length_m=profile.poolLengthM,
        resolved_start_mode=profile.startMode,
        stroke=profile.stroke,
        total_distance_m=profile.totalDistanceM,
    )


def _compile_1_1(profile):  # noqa: ANN001, ANN202
    return compile_continuous_pace_profile(
        profile,
        pool_length_m=profile.poolLengthM,
        resolved_start_mode=profile.startMode,
        stroke=profile.stroke,
        total_distance_m=profile.totalDistanceM,
    )


def test_migration_does_not_mutate_input() -> None:
    legacy = _legacy()
    before = legacy.model_dump(mode="json")
    migrate_approved_pace_profile_1_0_to_1_1(legacy)
    assert legacy.model_dump(mode="json") == before


def test_migration_preserves_total_and_leg_durations() -> None:
    legacy = _legacy()
    migrated = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    old_tl = _compile_1_0(legacy)
    new_tl = _compile_1_1(migrated).timeline
    assert abs(old_tl.totalActiveDurationSec - new_tl.totalActiveDurationSec) < 1e-6
    old_50 = target_active_time_at_distance(old_tl, 50.0).elapsedActiveSec
    new_50 = target_active_time_at_distance(new_tl, 50.0).elapsedActiveSec
    assert abs(old_50 - new_50) < 1e-6
    assert abs(old_50 - 40.0) < 1e-6


def test_migration_bit_identical_no_smoothing() -> None:
    """Migrated constant-speed execution matches legacy at every official wall."""
    legacy = _legacy()
    migrated = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    old_tl = _compile_1_0(legacy)
    new_tl = _compile_1_1(migrated).timeline
    for wall in (25.0, 50.0, 75.0, 100.0):
        a = target_active_time_at_distance(old_tl, wall).elapsedActiveSec
        b = target_active_time_at_distance(new_tl, wall).elapsedActiveSec
        assert abs(a - b) < 1e-9
    assert abs(old_tl.totalActiveDurationSec - new_tl.totalActiveDurationSec) < 1e-9
    assert migrated.curve.representation.value == "CONSTANT_SPEED"


def test_migration_provenance() -> None:
    migrated = migrate_approved_pace_profile_1_0_to_1_1(_legacy())
    prov = migrated.curveProvenance
    assert prov.migratedFromSchemaVersion == "1.0"
    assert prov.migrationVersion == MIGRATION_VERSION
    assert prov.legacyProfileId == "legacy1"
    assert prov.legacyProfileVersion == "1"


def test_migration_preserves_authority_and_lock() -> None:
    legacy = _legacy()
    migrated = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    assert migrated.source is legacy.source
    assert migrated.approvalStatus is legacy.approvalStatus
    assert migrated.coachLocked == legacy.coachLocked
    assert migrated.poolLengthM == legacy.poolLengthM
    assert migrated.startMode is legacy.startMode
    assert migrated.stroke is legacy.stroke


def test_25m_and_50m_independent_compile() -> None:
    m25 = migrate_approved_pace_profile_1_0_to_1_1(_legacy(pool=25))
    m50 = migrate_approved_pace_profile_1_0_to_1_1(_legacy(pool=50))
    assert _compile_1_1(m25).validationSummary.validationPassed
    assert _compile_1_1(m50).validationSummary.validationPassed


def test_25m_profile_cannot_run_in_50m_context() -> None:
    from swimcore.pacing.profile_compiler import ProfileCompilationError

    m25 = migrate_approved_pace_profile_1_0_to_1_1(_legacy(pool=25))
    with pytest.raises(ProfileCompilationError, match="pool"):
        compile_continuous_pace_profile(
            m25,
            pool_length_m=50,
            resolved_start_mode=m25.startMode,
            stroke=m25.stroke,
            total_distance_m=m25.totalDistanceM,
        )
