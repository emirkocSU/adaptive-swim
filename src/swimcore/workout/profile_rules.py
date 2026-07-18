"""Semantic validation for approved pace profiles (§21 rule codes).

Pure and deterministic. Produces machine-readable ``ValidationIssue`` objects (not
exceptions) so the same defects the compiler would raise on are also surfaced as issues for
the validation report. Rule codes come from ``RuleCode`` (RULE-013 family).
"""

from __future__ import annotations

from contracts._base import FLOAT_TOLERANCE
from contracts.enums import IssueSeverity, ProfileApprovalStatus, StartMode, Stroke
from contracts.errors import ValidationIssue
from contracts.pace_profiles import LIVE_ELIGIBLE_APPROVAL_STATUSES, ApprovedPaceProfile
from swimcore.workout.rules import RuleCode


def _err(path: str, rule: RuleCode, message: str) -> ValidationIssue:
    return ValidationIssue(
        path=path, rule=rule.value, message=message, severity=IssueSeverity.ERROR
    )


def validate_approved_pace_profile(
    profile: ApprovedPaceProfile,
    *,
    pool_length_m: int,
    resolved_start_mode: StartMode,
    stroke: Stroke,
    workout_distance_m: float,
    allow_default_model: bool = False,
) -> list[ValidationIssue]:
    """Return all semantic issues for running ``profile`` in the given workout context."""
    issues: list[ValidationIssue] = []

    if profile.approvalStatus not in LIVE_ELIGIBLE_APPROVAL_STATUSES:
        status = getattr(profile.approvalStatus, "value", profile.approvalStatus)
        issues.append(
            _err(
                "approvalStatus",
                RuleCode.PACE_PROFILE_NOT_APPROVED,
                f"profile approvalStatus {status} is not live-eligible",
            )
        )
    if (
        profile.approvalStatus is ProfileApprovalStatus.APPROVED_BY_EXPLICIT_DEFAULT_POLICY
        and not allow_default_model
    ):
        issues.append(
            _err(
                "approvalStatus",
                RuleCode.DEFAULT_MODEL_PROFILE_NOT_OPTED_IN,
                "default-model profile requires an explicit opt-in policy",
            )
        )
    if profile.poolLengthM != pool_length_m:
        issues.append(
            _err(
                "poolLengthM",
                RuleCode.PACE_PROFILE_POOL_MISMATCH,
                f"profile pool {profile.poolLengthM} != workout pool {pool_length_m}",
            )
        )
    if profile.startMode is not resolved_start_mode:
        issues.append(
            _err(
                "startMode",
                RuleCode.PACE_PROFILE_START_MODE_MISMATCH,
                f"profile start mode {profile.startMode.value} != resolved "
                f"{resolved_start_mode.value}",
            )
        )
    if profile.stroke is not stroke:
        issues.append(
            _err(
                "stroke",
                RuleCode.PACE_PROFILE_STROKE_MISMATCH,
                f"profile stroke {profile.stroke.value} != workout stroke {stroke.value}",
            )
        )

    # coverage / overlap across legs
    legs = profile.legs
    if abs(legs[0].fromM) > FLOAT_TOLERANCE:
        issues.append(
            _err("legs[0].fromM", RuleCode.PACE_PROFILE_COVERAGE_GAP, "first leg must start at 0 m")
        )
    for i in range(len(legs) - 1):
        gap = legs[i + 1].fromM - legs[i].toM
        if gap > FLOAT_TOLERANCE:
            issues.append(
                _err(
                    f"legs[{i + 1}].fromM",
                    RuleCode.PACE_PROFILE_COVERAGE_GAP,
                    f"gap between leg {i} and leg {i + 1}",
                )
            )
        elif gap < -FLOAT_TOLERANCE:
            issues.append(
                _err(
                    f"legs[{i + 1}].fromM",
                    RuleCode.PACE_PROFILE_OVERLAP,
                    f"overlap between leg {i} and leg {i + 1}",
                )
            )

    # per-leg constant-pace duration consistency
    for leg in legs:
        expected = leg.targetDurationSec * 100.0 / leg.legDistanceM * leg.legDistanceM / 100.0
        if abs(expected - leg.targetDurationSec) > FLOAT_TOLERANCE:
            issues.append(
                _err(
                    f"legs[{leg.legIndex}].targetDurationSec",
                    RuleCode.PACE_PROFILE_DURATION_MISMATCH,
                    f"leg {leg.legIndex} duration inconsistent",
                )
            )

    # total time reconciliation
    total = sum(leg.targetDurationSec for leg in legs)
    if abs(total - profile.targetTotalTimeSec) > FLOAT_TOLERANCE:
        issues.append(
            _err(
                "targetTotalTimeSec",
                RuleCode.PACE_PROFILE_TOTAL_TIME_MISMATCH,
                f"leg durations sum to {total}, not targetTotalTimeSec "
                f"{profile.targetTotalTimeSec}",
            )
        )
    # coverage vs the workout's official distance
    if abs(profile.totalDistanceM - workout_distance_m) > FLOAT_TOLERANCE:
        issues.append(
            _err(
                "legs",
                RuleCode.PACE_PROFILE_COVERAGE_GAP,
                f"profile covers {profile.totalDistanceM} m, workout total is "
                f"{workout_distance_m} m",
            )
        )
    return issues
