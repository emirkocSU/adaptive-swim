"""Deterministic pace-math engine (Commit 4).

Pure, side-effect-free, clock-independent active-swimming pace mathematics. Converts a
workout plan into a distance/active-time target pace timeline. Rest, StopPause, and real
elapsed time are **not** part of this layer.
"""

from swimcore.pacing.continuous_curve import (
    ContinuousCurveValidationContext,
    build_evaluable_curve,
)
from swimcore.pacing.continuous_migration import (
    migrate_approved_pace_profile_1_0_to_1_1,
)
from swimcore.pacing.continuous_profile_compiler import (
    CONTINUOUS_COMPILER_VERSION,
    CONTINUOUS_CURVE_MAX_STEP_M,
    CURVE_TIME_TOLERANCE_SEC,
    CompiledContinuousPacePlan,
    compile_continuous_pace_profile,
)
from swimcore.pacing.curves import (
    ControlledStartProfile,
    resolve_curve_endpoints,
    segment_active_duration_sec,
)
from swimcore.pacing.errors import (
    DistanceOutsideTimelineError,
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceCurveError,
    InvalidPaceError,
    InvalidPoolLengthError,
    PaceMathError,
    TimeOutsideTimelineError,
    UnsupportedPaceModeError,
)
from swimcore.pacing.math import distance_for_duration, duration_for_distance
from swimcore.pacing.pchip import PchipError, PchipInterpolator, build_pchip
from swimcore.pacing.profile_compiler import (
    ProfileCompilationError,
    compile_approved_pace_profile,
)
from swimcore.pacing.profile_selection import (
    AmbiguousPaceProfileSelectionError,
    CoachLockedProfileOverrideError,
    NoLiveEligiblePaceProfileError,
    PaceProfileSelectionError,
    ProfileSelectionPolicy,
    select_live_pace_profile,
)
from swimcore.pacing.timeline import (
    compile_pace_timeline,
    ghost_distance_at_active_time,
    is_wall_boundary,
    next_wall_boundary,
    previous_wall_boundary,
    target_active_time_at_distance,
)
from swimcore.pacing.types import (
    EPSILON,
    DistanceAtTimeResult,
    PaceInterval,
    PacePoint,
    PaceTimeline,
    TimeAtDistanceResult,
)

__all__ = [
    "CONTINUOUS_COMPILER_VERSION",
    "CONTINUOUS_CURVE_MAX_STEP_M",
    "CURVE_TIME_TOLERANCE_SEC",
    "EPSILON",
    "AmbiguousPaceProfileSelectionError",
    "CoachLockedProfileOverrideError",
    "CompiledContinuousPacePlan",
    "ContinuousCurveValidationContext",
    "ControlledStartProfile",
    "PchipError",
    "PchipInterpolator",
    "build_evaluable_curve",
    "build_pchip",
    "compile_continuous_pace_profile",
    "migrate_approved_pace_profile_1_0_to_1_1",
    "DistanceAtTimeResult",
    "DistanceOutsideTimelineError",
    "InvalidDistanceError",
    "InvalidDurationError",
    "InvalidPaceCurveError",
    "InvalidPaceError",
    "InvalidPoolLengthError",
    "NoLiveEligiblePaceProfileError",
    "PaceInterval",
    "PaceMathError",
    "PaceProfileSelectionError",
    "PacePoint",
    "PaceTimeline",
    "ProfileCompilationError",
    "ProfileSelectionPolicy",
    "TimeAtDistanceResult",
    "TimeOutsideTimelineError",
    "UnsupportedPaceModeError",
    "compile_approved_pace_profile",
    "compile_pace_timeline",
    "distance_for_duration",
    "duration_for_distance",
    "ghost_distance_at_active_time",
    "is_wall_boundary",
    "next_wall_boundary",
    "previous_wall_boundary",
    "resolve_curve_endpoints",
    "segment_active_duration_sec",
    "select_live_pace_profile",
    "target_active_time_at_distance",
]
