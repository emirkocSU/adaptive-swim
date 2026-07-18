"""Deterministic compiler for approved distance-specific pace profiles (ADR-034).

Executes a *previously approved* ``ApprovedPaceProfile`` — it never generates one and never
calls model inference. Each leg is expanded at a constant leg pace
(``targetDurationSec * 100 / legDistanceM``); rest / StopPause / lifecycle-pause time is not
part of this timeline. The same profile always yields a bit-identical timeline.

Legs are NOT official wall splits. The compiled ``PaceInterval`` carries ``profileLegIndex``
and profile provenance so downstream consumers can distinguish leg boundaries from official
walls (which come only from verified wall splits, ADR-036).
"""

from __future__ import annotations

from contracts.enums import StartMode, Stroke
from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing.curves import curve_duration
from swimcore.pacing.errors import InvalidPaceCurveError
from swimcore.pacing.types import PaceInterval, PaceTimeline


class ProfileCompilationError(InvalidPaceCurveError):
    """An approved profile is inconsistent with its resolved workout context."""


def compile_approved_pace_profile(
    profile: ApprovedPaceProfile,
    *,
    pool_length_m: int,
    resolved_start_mode: StartMode,
    stroke: Stroke,
    total_distance_m: float | None = None,
) -> PaceTimeline:
    """Compile an approved profile into an active-time pace timeline.

    The profile's pool length, start mode, and stroke must match the resolved workout
    context; the leg coverage must reach the workout total distance (when supplied).
    """
    if not profile.is_live_eligible:
        raise ProfileCompilationError(
            f"profile {profile.profileId} is not live-eligible "
            f"(approvalStatus={profile.approvalStatus})"
        )
    if profile.poolLengthM != pool_length_m:
        raise ProfileCompilationError(
            f"profile pool {profile.poolLengthM} != workout pool {pool_length_m}"
        )
    if profile.startMode is not resolved_start_mode:
        raise ProfileCompilationError(
            f"profile start mode {profile.startMode} != resolved {resolved_start_mode}"
        )
    if profile.stroke is not stroke:
        raise ProfileCompilationError(f"profile stroke {profile.stroke} != workout stroke {stroke}")
    if total_distance_m is not None and abs(profile.totalDistanceM - total_distance_m) > 1e-6:
        raise ProfileCompilationError(
            f"profile covers {profile.totalDistanceM} m, workout total is {total_distance_m} m"
        )

    intervals: list[PaceInterval] = []
    total_active = 0.0
    for leg in profile.legs:
        length = leg.legDistanceM
        pace = leg.paceSecPer100M
        duration = curve_duration(length, pace, pace)
        # duration must match the declared leg duration (constant-pace execution)
        if abs(duration - leg.targetDurationSec) > 1e-6:
            raise ProfileCompilationError(
                f"leg {leg.legIndex}: computed duration {duration} != "
                f"declared {leg.targetDurationSec}"
            )
        intervals.append(
            PaceInterval(
                fromM=leg.fromM,
                toM=leg.toM,
                startPaceSecPer100M=pace,
                endPaceSecPer100M=pace,
                mode="approved_profile_leg",
                activeDurationSec=duration,
                blockIndex=0,
                repeatIndex=0,
                segmentIndex=leg.legIndex,
                profileLegIndex=leg.legIndex,
                startMode=resolved_start_mode.value,
                profileId=profile.profileId,
                profileSource=profile.source.value,
                profileType=profile.profileType.value,
                phaseType=leg.phaseType.value,
            )
        )
        total_active += duration

    if abs(total_active - profile.targetTotalTimeSec) > 1e-6:
        raise ProfileCompilationError(
            f"compiled total {total_active} != profile targetTotalTimeSec "
            f"{profile.targetTotalTimeSec}"
        )
    return PaceTimeline(
        totalDistanceM=profile.totalDistanceM,
        totalActiveDurationSec=total_active,
        intervals=tuple(intervals),
    )


__all__ = [
    "ProfileCompilationError",
    "compile_approved_pace_profile",
]
