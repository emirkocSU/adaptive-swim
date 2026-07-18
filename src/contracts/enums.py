"""All enumerations for the Adaptive Swim contracts.

Terminology note: the general runtime stop behaviour is **StopPause**. "Incident" survives
only as a *trigger* (`StopPauseTrigger.MANUAL_INCIDENT`), never as a behaviour name.
"""

from __future__ import annotations

from enum import StrEnum


class _StrEnum(StrEnum):
    """Base for string-valued enums (stable JSON output via the assigned value)."""


# --------------------------------------------------------------------------- workout
class Stroke(_StrEnum):
    freestyle = "freestyle"
    backstroke = "backstroke"
    breaststroke = "breaststroke"
    butterfly = "butterfly"
    medley = "medley"
    mixed = "mixed"


# --------------------------------------------------------------------------- start mode / goal (Workout 1.1)
class StartMode(_StrEnum):
    """How a length / repeat begins. Affects the first-segment pace distribution.

    The official distance at start is always 0 m regardless of start mode (ADR-036).
    """

    DIVE_START = "DIVE_START"
    IN_WATER_PUSH_START = "IN_WATER_PUSH_START"
    IN_WATER_STATIC_START = "IN_WATER_STATIC_START"


class WorkoutGoal(_StrEnum):
    RACE_PACE = "RACE_PACE"
    THRESHOLD = "THRESHOLD"
    AEROBIC = "AEROBIC"
    TECHNIQUE = "TECHNIQUE"
    TEST = "TEST"
    RECOVERY = "RECOVERY"
    MAX_PERFORMANCE = "MAX_PERFORMANCE"
    CONTROLLED_RACE_EFFORT = "CONTROLLED_RACE_EFFORT"
    CUSTOM = "CUSTOM"


# --------------------------------------------------------------------------- pace profile taxonomy (ADR-034)
class PaceProfileType(_StrEnum):
    SPRINT_POSITIVE_SPLIT = "SPRINT_POSITIVE_SPLIT"
    FAST_START_HOLD = "FAST_START_HOLD"
    FAST_START_CONTROLLED_FADE = "FAST_START_CONTROLLED_FADE"
    EVEN_PACE = "EVEN_PACE"
    CONTROLLED_START = "CONTROLLED_START"
    PROGRESSIVE_BUILD = "PROGRESSIVE_BUILD"
    NEGATIVE_SPLIT = "NEGATIVE_SPLIT"
    FINAL_ACCELERATION = "FINAL_ACCELERATION"
    CUSTOM_COACH_PROFILE = "CUSTOM_COACH_PROFILE"
    MODEL_GENERATED_CUSTOM = "MODEL_GENERATED_CUSTOM"
    DISTANCE_SPECIFIC_MIXED = "DISTANCE_SPECIFIC_MIXED"


class PaceProfileSource(_StrEnum):
    """Authoritative priority (highest first):

    COACH_AUTHORED > COACH_APPROVED_MODEL > DEFAULT_MODEL_GENERATED.
    TEMPLATE and LEGACY_SEGMENTS are positioned explicitly by the selector.
    """

    COACH_AUTHORED = "COACH_AUTHORED"
    COACH_APPROVED_MODEL = "COACH_APPROVED_MODEL"
    DEFAULT_MODEL_GENERATED = "DEFAULT_MODEL_GENERATED"
    TEMPLATE = "TEMPLATE"
    LEGACY_SEGMENTS = "LEGACY_SEGMENTS"


class ProfileApprovalStatus(_StrEnum):
    DRAFT = "DRAFT"
    COACH_APPROVED = "COACH_APPROVED"
    COACH_LOCKED = "COACH_LOCKED"
    APPROVED_BY_EXPLICIT_DEFAULT_POLICY = "APPROVED_BY_EXPLICIT_DEFAULT_POLICY"
    REJECTED = "REJECTED"


class PaceProfilePhase(_StrEnum):
    """Analytical phase of a profile leg. Legs are NOT official wall splits."""

    START_UNDERWATER = "START_UNDERWATER"
    SURFACE_SWIM = "SURFACE_SWIM"
    TURN_TRANSITION = "TURN_TRANSITION"
    MID_RACE = "MID_RACE"
    FINAL_ACCELERATION = "FINAL_ACCELERATION"
    FINISH = "FINISH"
    CUSTOM = "CUSTOM"


class TotalTimeReconciliationMode(_StrEnum):
    """Editor-layer only. ALLOW_INCONSISTENT_DRAFT never reaches live runtime."""

    KEEP_TOTAL_REDISTRIBUTE = "KEEP_TOTAL_REDISTRIBUTE"
    UPDATE_TOTAL = "UPDATE_TOTAL"
    ALLOW_INCONSISTENT_DRAFT = "ALLOW_INCONSISTENT_DRAFT"


class ProfileGenerationMode(_StrEnum):
    """Coach-screen authoring mode (Phase 2 UI; contract-only in Phase 1)."""

    AUTO_GENERATE = "AUTO_GENERATE"
    GENERATE_AND_EDIT = "GENERATE_AND_EDIT"
    MANUAL_PROFILE = "MANUAL_PROFILE"
    TEMPLATE = "TEMPLATE"


# --------------------------------------------------------------------------- physiology (advisory only)
class HrControlMode(_StrEnum):
    OFF = "OFF"
    ADVISORY = "ADVISORY"


class EffortTargetType(_StrEnum):
    HR_ZONE = "HR_ZONE"
    MAX_HR_PERCENT_RANGE = "MAX_HR_PERCENT_RANGE"
    AEROBIC_THRESHOLD = "AEROBIC_THRESHOLD"
    ANAEROBIC_THRESHOLD = "ANAEROBIC_THRESHOLD"
    RPE = "RPE"
    CONTROLLED_RACE_EFFORT = "CONTROLLED_RACE_EFFORT"
    MAX_PERFORMANCE = "MAX_PERFORMANCE"


# --------------------------------------------------------------------------- official distance authority (ADR-036)
class OfficialDistanceAuthority(_StrEnum):
    WORKOUT_GEOMETRY = "WORKOUT_GEOMETRY"
    WALL_VERIFICATION = "WALL_VERIFICATION"
    COMPLETED_LENGTH_COUNT = "COMPLETED_LENGTH_COUNT"
    EXTERNAL_VERIFIED_WALL = "EXTERNAL_VERIFIED_WALL"


class PaceMode(_StrEnum):
    even_pace = "even_pace"
    controlled_start = "controlled_start"
    progressive = "progressive"
    negative_split_part = "negative_split_part"


class FeedbackCapability(_StrEnum):
    SHOW_GHOST = "SHOW_GHOST"
    SHOW_GAP_AT_WALL = "SHOW_GAP_AT_WALL"
    SHOW_CONTINUOUS_GAP = "SHOW_CONTINUOUS_GAP"


class SetLabel(_StrEnum):
    warmup = "warmup"
    main = "main"
    technique = "technique"
    cooldown = "cooldown"
    custom = "custom"


class RestType(_StrEnum):
    none = "none"
    fixed = "fixed"
    interval = "interval"


class AdaptationMode(_StrEnum):
    off = "off"
    suggest_only = "suggest_only"
    bounded_auto = "bounded_auto"


class AdaptationSource(_StrEnum):
    rule_based = "rule_based"
    ml = "ml"


class GhostSourceType(_StrEnum):
    plan = "plan"
    personal_best = "personal_best"
    past_session = "past_session"
    coach_benchmark = "coach_benchmark"


# --------------------------------------------------------------------------- pacing / safety
class PaceTargetOrigin(_StrEnum):
    PLAN = "PLAN"
    COACH_OVERRIDE = "COACH_OVERRIDE"
    RULE_ADAPTATION = "RULE_ADAPTATION"
    ML_ADAPTATION = "ML_ADAPTATION"
    COACH_PACING_RESET = "COACH_PACING_RESET"


class PaceRequestSource(_StrEnum):
    COACH_MANUAL = "COACH_MANUAL"
    RULE_BASED = "RULE_BASED"
    ML = "ML"


class ControlAdaptationSource(_StrEnum):
    rule_based = "rule_based"
    ml = "ml"
    none = "none"


class ControlDecisionAction(_StrEnum):
    APPLY = "APPLY"
    CLAMP = "CLAMP"
    ABSTAIN = "ABSTAIN"
    REJECT = "REJECT"
    SUGGEST = "SUGGEST"
    KEEP_PLAN = "KEEP_PLAN"


class ReasonCode(_StrEnum):
    ADAPTATION_OFF = "ADAPTATION_OFF"
    INFERENCE_UNAVAILABLE = "INFERENCE_UNAVAILABLE"
    MODEL_NOT_ELIGIBLE = "MODEL_NOT_ELIGIBLE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SENSOR_QUALITY = "SENSOR_QUALITY"
    COLD_START = "COLD_START"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    CLAMPED = "CLAMPED"
    MAX_DELTA_CLAMPED = "MAX_DELTA_CLAMPED"
    CONFLICT_STREAK = "CONFLICT_STREAK"
    SUGGESTED = "SUGGESTED"
    BOUNDED_APPLY = "BOUNDED_APPLY"
    COACH_OVERRIDE = "COACH_OVERRIDE"
    CLAMPED_TO_BOUNDS = "CLAMPED_TO_BOUNDS"
    APPLIED = "APPLIED"
    # --- Workout 1.1 / approved-profile mainline (§12) ---
    COACH_PROFILE_LOCKED = "COACH_PROFILE_LOCKED"
    ML_CONFIDENCE_MISSING = "ML_CONFIDENCE_MISSING"
    DATA_QUALITY_MISSING = "DATA_QUALITY_MISSING"
    PROFILE_SOURCE_NOT_ELIGIBLE = "PROFILE_SOURCE_NOT_ELIGIBLE"
    CURRENT_PROFILE_LEG_TARGET = "CURRENT_PROFILE_LEG_TARGET"


# --------------------------------------------------------------------------- ghost
class GhostOperationalState(_StrEnum):
    ACTIVE = "ACTIVE"
    STOP_PAUSED = "STOP_PAUSED"


class GhostAlignmentMode(_StrEnum):
    CONTINUE_PLAN = "CONTINUE_PLAN"
    CONTROLLED_STOP_PAUSE_ALIGNMENT = "CONTROLLED_STOP_PAUSE_ALIGNMENT"
    COACH_PACING_RESET_AT_WALL = "COACH_PACING_RESET_AT_WALL"


# --------------------------------------------------------------------------- stop pause
class StopPauseTrigger(_StrEnum):
    MANUAL_INCIDENT = "MANUAL_INCIDENT"
    LONG_STOP_THRESHOLD = "LONG_STOP_THRESHOLD"
    COACH_STOP = "COACH_STOP"
    SENSOR_STOP = "SENSOR_STOP"


class StopDetectionSource(_StrEnum):
    COACH = "COACH"
    SENSOR = "SENSOR"
    ESTIMATOR = "ESTIMATOR"
    THRESHOLD = "THRESHOLD"


class StopSignalQuality(_StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class AlignmentSource(_StrEnum):
    TRACKED_POSITION = "TRACKED_POSITION"
    ESTIMATED_POSITION = "ESTIMATED_POSITION"
    COACH_MARK = "COACH_MARK"
    WALL_RECONCILIATION = "WALL_RECONCILIATION"
    UNKNOWN = "UNKNOWN"


class AlignmentQuality(_StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class StopStartTimeQuality(_StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------- splits
class SplitSource(_StrEnum):
    BUTTON = "BUTTON"
    COACH_TAP = "COACH_TAP"
    TOUCHPAD = "TOUCHPAD"
    WEARABLE = "WEARABLE"
    SIMULATED = "SIMULATED"


class SplitQualityFlag(_StrEnum):
    VERIFIED_HIGH = "VERIFIED_HIGH"
    RELIABLE = "RELIABLE"
    MANUAL_UNVERIFIED = "MANUAL_UNVERIFIED"
    ESTIMATED = "ESTIMATED"
    INVALID = "INVALID"


class VerificationSource(_StrEnum):
    SECOND_TIMER = "SECOND_TIMER"
    VIDEO = "VIDEO"
    TOUCHPAD = "TOUCHPAD"
    DUAL_OBSERVER = "DUAL_OBSERVER"


# --------------------------------------------------------------------------- analytics
class AnalyticsExclusionReason(_StrEnum):
    UNRELIABLE_STOP_TIMING = "UNRELIABLE_STOP_TIMING"
    UNRELIABLE_ALIGNMENT = "UNRELIABLE_ALIGNMENT"


# --------------------------------------------------------------------------- events
class EventType(_StrEnum):
    WorkoutValidated = "WorkoutValidated"
    SessionCreated = "SessionCreated"
    SessionArmed = "SessionArmed"
    SessionStarted = "SessionStarted"
    SessionPaused = "SessionPaused"
    SessionResumed = "SessionResumed"
    SessionCompleted = "SessionCompleted"
    SessionAborted = "SessionAborted"
    SplitRecorded = "SplitRecorded"
    SplitVerified = "SplitVerified"
    StopDetected = "StopDetected"
    LongStopConfirmed = "LongStopConfirmed"
    StopPauseStarted = "StopPauseStarted"
    StopPauseResolved = "StopPauseResolved"
    PaceTargetChanged = "PaceTargetChanged"
    CoachPacingResetRequested = "CoachPacingResetRequested"
    CoachPacingResetApplied = "CoachPacingResetApplied"
    ControlDecisionMade = "ControlDecisionMade"
    SessionRecovered = "SessionRecovered"
    # --- pace-profile / planning lifecycle (§13; authored later, contracts now) ---
    PaceProfileGenerated = "PaceProfileGenerated"
    PaceProfileEdited = "PaceProfileEdited"
    PaceProfileApproved = "PaceProfileApproved"
    PaceProfileRejected = "PaceProfileRejected"
    PaceProfileSelected = "PaceProfileSelected"
    PaceProfileLocked = "PaceProfileLocked"


# --------------------------------------------------------------------------- external data
class ExternalDataDomain(_StrEnum):
    ELITE_RACE = "ELITE_RACE"
    TRAINING_EXPORT = "TRAINING_EXPORT"
    WEARABLE_SENSOR = "WEARABLE_SENSOR"
    ADAPTIVE_SWIM_SESSION = "ADAPTIVE_SWIM_SESSION"
    SYNTHETIC_SIMULATION = "SYNTHETIC_SIMULATION"


class ExternalDataRole(_StrEnum):
    L1_RACE_PACING_PRIOR = "L1_RACE_PACING_PRIOR"
    L2_WEARABLE_PRETRAINING = "L2_WEARABLE_PRETRAINING"
    L3_USER_CONSENTED_EXPORT = "L3_USER_CONSENTED_EXPORT"
    L4_SIMULATOR_SYNTHETIC = "L4_SIMULATOR_SYNTHETIC"
    L5_ADAPTIVE_SWIM_PROPRIETARY = "L5_ADAPTIVE_SWIM_PROPRIETARY"


class VerificationStatus(_StrEnum):
    ALLOWED = "ALLOWED"
    PROHIBITED = "PROHIBITED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    TBD_VERIFICATION_REQUIRED = "TBD_VERIFICATION_REQUIRED"


class IssueSeverity(_StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
