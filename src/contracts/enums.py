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
