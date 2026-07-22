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


# --------------------------------------------------------------------------- continuous pace curves (ADR-038)
class ContinuousPacePhaseType(_StrEnum):
    """Within-length phase of a continuous pace curve (ADR-038, Workout 1.1 pacing).

    A phase boundary is NOT an official wall boundary and never an official split; it is an
    analytical span used to shape the within-length target-speed curve. Distinct from the
    1.0 ``PaceProfilePhase`` enum, which is preserved unchanged for the 1.0 contract.
    """

    START_ACCELERATION = "START_ACCELERATION"
    START_UNDERWATER = "START_UNDERWATER"
    BREAKOUT_TRANSITION = "BREAKOUT_TRANSITION"
    SURFACE_SWIM = "SURFACE_SWIM"
    MID_LENGTH_ADJUSTMENT = "MID_LENGTH_ADJUSTMENT"
    WALL_APPROACH = "WALL_APPROACH"
    TURN_ENTRY = "TURN_ENTRY"
    TURN_TRANSITION = "TURN_TRANSITION"
    TURN_UNDERWATER = "TURN_UNDERWATER"
    FINAL_ACCELERATION = "FINAL_ACCELERATION"
    FINISH = "FINISH"
    CUSTOM = "CUSTOM"


class PaceCurveRepresentation(_StrEnum):
    """Continuous curve representation (ADR-038).

    Phase 1 supports exactly two: ``PCHIP`` (authoritative for native continuous profiles)
    and ``CONSTANT_SPEED`` (legacy-migration and explicit templates only). No generic
    unbounded cubic spline is offered.
    """

    PCHIP = "PCHIP"
    CONSTANT_SPEED = "CONSTANT_SPEED"


class TargetTimeSource(_StrEnum):
    """Where a continuous profile's target total time came from (ADR-038)."""

    COACH = "COACH"
    MODEL_RECOMMENDED = "MODEL_RECOMMENDED"
    TEMPLATE = "TEMPLATE"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"


class ContinuousCurveGenerationMode(_StrEnum):
    """How the continuous curve was produced (ADR-038 provenance)."""

    AUTO_GENERATE = "AUTO_GENERATE"
    GENERATE_AND_EDIT = "GENERATE_AND_EDIT"
    MANUAL_SPLIT_CONSTRAINTS = "MANUAL_SPLIT_CONSTRAINTS"
    MANUAL_CONTINUOUS_PROFILE = "MANUAL_CONTINUOUS_PROFILE"
    TEMPLATE = "TEMPLATE"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"


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


# --------------------------------------------------------------------------- curve evidence (ADR-039)
class CurveOrigin(_StrEnum):
    """Who/what produced a continuous target-envelope curve."""

    COACH_FIXED = "COACH_FIXED"
    EVENT_MEDIAN_PRIOR = "EVENT_MEDIAN_PRIOR"
    RACE_MODEL_PRIOR = "RACE_MODEL_PRIOR"
    RACE_PRIOR_TRAINING_CORRECTED = "RACE_PRIOR_TRAINING_CORRECTED"
    FORM_PERSONALIZED = "FORM_PERSONALIZED"
    COACH_EDITED = "COACH_EDITED"
    TEMPLATE = "TEMPLATE"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"


class CurveEvidenceLevel(_StrEnum):
    """How much real evidence stands behind a curve's *shape*."""

    DETERMINISTIC_BASELINE = "DETERMINISTIC_BASELINE"
    COARSE_SPLIT_DERIVED = "COARSE_SPLIT_DERIVED"
    CONTROLLED_STUDY_AUGMENTED = "CONTROLLED_STUDY_AUGMENTED"
    TRAINING_EXPORT_PERSONALIZED = "TRAINING_EXPORT_PERSONALIZED"
    PILOT_PERSONALIZED = "PILOT_PERSONALIZED"


class VisualShapeSource(_StrEnum):
    """Where the within-length visual shape of the ghost curve comes from."""

    CONSTANT_SEGMENT = "CONSTANT_SEGMENT"
    BOUNDED_TEMPLATE = "BOUNDED_TEMPLATE"
    LEARNED_COARSE_LATENT = "LEARNED_COARSE_LATENT"
    FORM_DERIVED = "FORM_DERIVED"
    PERSONALIZED_FORM_DERIVED = "PERSONALIZED_FORM_DERIVED"
    COACH_AUTHORED = "COACH_AUTHORED"


# --------------------------------------------------------------------------- dataset assets (ADR-039)
class DatasetRole(_StrEnum):
    RACE_PACING_PRIOR = "RACE_PACING_PRIOR"
    TRAINING_DOMAIN_CORRECTION = "TRAINING_DOMAIN_CORRECTION"
    REPEAT_FATIGUE_PRIOR = "REPEAT_FATIGUE_PRIOR"
    FATIGUE_SHAPE_PRIOR = "FATIGUE_SHAPE_PRIOR"
    TECHNIQUE_DECLINE_PRIOR = "TECHNIQUE_DECLINE_PRIOR"
    SENSOR_ENCODER_RESEARCH = "SENSOR_ENCODER_RESEARCH"
    SENSOR_FEATURE_RESEARCH = "SENSOR_FEATURE_RESEARCH"
    TECHNIQUE_FEATURE_RESEARCH = "TECHNIQUE_FEATURE_RESEARCH"
    FUTURE_WEARABLE_CALIBRATION = "FUTURE_WEARABLE_CALIBRATION"
    PERSONAL_CALIBRATION_RESEARCH = "PERSONAL_CALIBRATION_RESEARCH"
    ADVISORY_AND_REPORTING_RESEARCH = "ADVISORY_AND_REPORTING_RESEARCH"
    RECOVERY_ADVISORY = "RECOVERY_ADVISORY"
    AUDITABLE_LONG_FORM_SOURCE = "AUDITABLE_LONG_FORM_SOURCE"
    PIPELINE_SMOKE_TEST_ONLY = "PIPELINE_SMOKE_TEST_ONLY"


class DatasetEligibility(_StrEnum):
    RESEARCH_ELIGIBLE = "RESEARCH_ELIGIBLE"
    PRODUCTION_ELIGIBLE = "PRODUCTION_ELIGIBLE"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"
    QUARANTINED = "QUARANTINED"
    SMOKE_TEST_ONLY = "SMOKE_TEST_ONLY"


class DatasetEvidenceLevel(_StrEnum):
    OFFICIAL_RACE_RESULT = "OFFICIAL_RACE_RESULT"
    CONTROLLED_STUDY = "CONTROLLED_STUDY"
    TRAINING_OBSERVATION = "TRAINING_OBSERVATION"
    PROCESSED_SENSOR_STATISTIC = "PROCESSED_SENSOR_STATISTIC"
    RAW_SENSOR_SAMPLE = "RAW_SENSOR_SAMPLE"
    UNPROVENANCED = "UNPROVENANCED"


class DatasetDomain(_StrEnum):
    OFFICIAL_RACE = "OFFICIAL_RACE"
    TRAINING = "TRAINING"
    CONTROLLED_STUDY = "CONTROLLED_STUDY"
    SENSOR_RESEARCH = "SENSOR_RESEARCH"
    INTERVENTION_STUDY = "INTERVENTION_STUDY"
    UNPROVENANCED = "UNPROVENANCED"


class DatasetGranularity(_StrEnum):
    RACE_SEGMENT = "RACE_SEGMENT"
    ATHLETE_WEEK = "ATHLETE_WEEK"
    SPRINT_REPEAT = "SPRINT_REPEAT"
    STUDY_SEGMENT = "STUDY_SEGMENT"
    MEASUREMENT_LONG = "MEASUREMENT_LONG"
    SENSOR_SAMPLE = "SENSOR_SAMPLE"
    SESSION_ROW = "SESSION_ROW"
    WINDOW_ROW = "WINDOW_ROW"


class LicenseEligibility(_StrEnum):
    VERIFIED_ALLOWED = "VERIFIED_ALLOWED"
    REPORTED_OPEN_UNVERIFIED = "REPORTED_OPEN_UNVERIFIED"
    MIXED_BY_SOURCE = "MIXED_BY_SOURCE"
    TBD_VERIFICATION_REQUIRED = "TBD_VERIFICATION_REQUIRED"
    BLOCKED = "BLOCKED"


class ModelTask(_StrEnum):
    RACE_PACING_PRIOR_TRAINING = "RACE_PACING_PRIOR_TRAINING"
    TRAINING_DOMAIN_CORRECTION_TRAINING = "TRAINING_DOMAIN_CORRECTION_TRAINING"
    REPEAT_FATIGUE_FORECASTING = "REPEAT_FATIGUE_FORECASTING"
    SENSOR_ENCODER_PRETRAINING = "SENSOR_ENCODER_PRETRAINING"
    ADVISORY_REPORTING_RESEARCH = "ADVISORY_REPORTING_RESEARCH"
    PIPELINE_SMOKE_TEST = "PIPELINE_SMOKE_TEST"


# --------------------------------------------------------------------------- forecasting (ADR-039)
class ForecastSuggestionMode(_StrEnum):
    """How a forecast may reach the coach. Forecasts never mutate the coach target."""

    SUGGEST_ONLY = "SUGGEST_ONLY"
    SAFE_BASELINE = "SAFE_BASELINE"
    BOUNDED_AUTO = "BOUNDED_AUTO"
