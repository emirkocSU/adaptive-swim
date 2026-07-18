"""Semantic workout rules — each a pure function returning a list of ``ValidationIssue``.

Signature: ``rule(workout, ctx, has_context) -> list[ValidationIssue]``. Rules never mutate
their inputs, never do I/O, and never raise for domain problems. Small floating-point
tolerance is used for boundary comparisons.
"""

from __future__ import annotations

from enum import StrEnum

from contracts._base import FLOAT_TOLERANCE, approx_equal
from contracts.enums import AdaptationMode, FeedbackCapability, IssueSeverity, PaceMode
from contracts.errors import ValidationIssue
from contracts.workout import (
    AnyWorkoutTemplate,
    PaceSegment,
    RepeatBlock,
    RestInterval,
)
from swimcore.workout.context import WorkoutValidationContext

_TOL = FLOAT_TOLERANCE
#: Below this positive rest margin (seconds) an interval is "tight" (WARNING not ERROR).
_TIGHT_REST_MARGIN_SEC = 2.0


class RuleCode(StrEnum):
    # RULE-001 contiguous coverage
    SEGMENT_GAP = "SEGMENT_GAP"
    SEGMENT_OVERLAP = "SEGMENT_OVERLAP"
    SEGMENT_START_NOT_ZERO = "SEGMENT_START_NOT_ZERO"
    SEGMENT_END_NOT_BLOCK_DISTANCE = "SEGMENT_END_NOT_BLOCK_DISTANCE"
    SEGMENT_REVERSED = "SEGMENT_REVERSED"
    # RULE-002 pool-length multiple
    DISTANCE_NOT_MULTIPLE_OF_POOL = "DISTANCE_NOT_MULTIPLE_OF_POOL"
    SEGMENT_BOUNDARY_NOT_AT_WALL = "SEGMENT_BOUNDARY_NOT_AT_WALL"
    # RULE-003 pace bounds direction
    TARGET_FASTER_THAN_FASTEST_ALLOWED = "TARGET_FASTER_THAN_FASTEST_ALLOWED"
    TARGET_SLOWER_THAN_SLOWEST_ALLOWED = "TARGET_SLOWER_THAN_SLOWEST_ALLOWED"
    # RULE-004 progressive mode
    PROGRESSIVE_REQUIRES_END_PACE = "PROGRESSIVE_REQUIRES_END_PACE"
    PROGRESSIVE_END_NOT_FASTER = "PROGRESSIVE_END_NOT_FASTER"
    END_PACE_ONLY_FOR_PROGRESSIVE = "END_PACE_ONLY_FOR_PROGRESSIVE"
    # RULE-005 adaptation bounds consistency
    ADAPTATION_BOUNDS_REVERSED = "ADAPTATION_BOUNDS_REVERSED"
    BOUNDED_AUTO_MISSING_FIELDS = "BOUNDED_AUTO_MISSING_FIELDS"
    ADAPTATION_BOUNDS_NO_ROOM = "ADAPTATION_BOUNDS_NO_ROOM"
    ADAPTATION_OFF_REDUNDANT_FIELDS = "ADAPTATION_OFF_REDUNDANT_FIELDS"
    # RULE-006 feedback capability
    UNSUPPORTED_FEEDBACK_CAPABILITY = "UNSUPPORTED_FEEDBACK_CAPABILITY"
    FEEDBACK_CAPABILITY_NOT_VERIFIED = "FEEDBACK_CAPABILITY_NOT_VERIFIED"
    # RULE-007 total distance
    TOTAL_DISTANCE_NON_POSITIVE = "TOTAL_DISTANCE_NON_POSITIVE"
    TOTAL_DISTANCE_EXCEEDS_MAX = "TOTAL_DISTANCE_EXCEEDS_MAX"
    # RULE-008 ghost source references
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    REFERENCE_NOT_VERIFIED = "REFERENCE_NOT_VERIFIED"
    # RULE-009 rest interval sanity
    REST_INTERVAL_NEGATIVE = "REST_INTERVAL_NEGATIVE"
    REST_INTERVAL_TIGHT = "REST_INTERVAL_TIGHT"
    # RULE-010 schema version
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    # RULE-011 controlled start
    CONTROLLED_START_PACE_REQUIRED = "CONTROLLED_START_PACE_REQUIRED"
    CONTROLLED_START_DIRECTION_INVALID = "CONTROLLED_START_DIRECTION_INVALID"
    START_PACE_NOT_ALLOWED_FOR_MODE = "START_PACE_NOT_ALLOWED_FOR_MODE"
    # RULE-012 negative split ordering
    NEGATIVE_SPLIT_ORDER_INVALID = "NEGATIVE_SPLIT_ORDER_INVALID"
    # RULE-013 Workout 1.1 start-mode / approved-profile semantics (§21)
    START_MODE_REQUIRED = "START_MODE_REQUIRED"
    START_OVERRIDE_NOT_ALLOWED = "START_OVERRIDE_NOT_ALLOWED"
    REPEAT_OVERRIDE_INDEX_INVALID = "REPEAT_OVERRIDE_INDEX_INVALID"
    PACE_PROFILE_NOT_APPROVED = "PACE_PROFILE_NOT_APPROVED"
    PACE_PROFILE_POOL_MISMATCH = "PACE_PROFILE_POOL_MISMATCH"
    PACE_PROFILE_START_MODE_MISMATCH = "PACE_PROFILE_START_MODE_MISMATCH"
    PACE_PROFILE_STROKE_MISMATCH = "PACE_PROFILE_STROKE_MISMATCH"
    PACE_PROFILE_COVERAGE_GAP = "PACE_PROFILE_COVERAGE_GAP"
    PACE_PROFILE_OVERLAP = "PACE_PROFILE_OVERLAP"
    PACE_PROFILE_DURATION_MISMATCH = "PACE_PROFILE_DURATION_MISMATCH"
    PACE_PROFILE_TOTAL_TIME_MISMATCH = "PACE_PROFILE_TOTAL_TIME_MISMATCH"
    DEFAULT_MODEL_PROFILE_NOT_OPTED_IN = "DEFAULT_MODEL_PROFILE_NOT_OPTED_IN"
    AMBIGUOUS_LIVE_PROFILE = "AMBIGUOUS_LIVE_PROFILE"
    PHYSIOLOGY_TARGET_INVALID = "PHYSIOLOGY_TARGET_INVALID"


def _issue(path: str, rule: RuleCode, message: str, severity: IssueSeverity) -> ValidationIssue:
    return ValidationIssue(path=path, rule=rule.value, message=message, severity=severity)


def _err(path: str, rule: RuleCode, message: str) -> ValidationIssue:
    return _issue(path, rule, message, IssueSeverity.ERROR)


def _warn(path: str, rule: RuleCode, message: str) -> ValidationIssue:
    return _issue(path, rule, message, IssueSeverity.WARNING)


# --------------------------------------------------------------------------- RULE-001
def rule_001_contiguous_coverage(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        segs = block.segments
        first = segs[0]
        if not approx_equal(first.fromM, 0.0):
            issues.append(
                _err(
                    f"blocks[{b}].segments[0].fromM",
                    RuleCode.SEGMENT_START_NOT_ZERO,
                    f"first segment must start at 0, got {first.fromM}",
                )
            )
        for s, seg in enumerate(segs):
            if seg.toM <= seg.fromM + _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s}].toM",
                        RuleCode.SEGMENT_REVERSED,
                        f"segment toM ({seg.toM}) must be greater than fromM ({seg.fromM})",
                    )
                )
        for s in range(len(segs) - 1):
            cur, nxt = segs[s], segs[s + 1]
            if nxt.fromM > cur.toM + _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s + 1}].fromM",
                        RuleCode.SEGMENT_GAP,
                        f"gap between segment {s} (ends {cur.toM}) and {s + 1} "
                        f"(starts {nxt.fromM})",
                    )
                )
            elif nxt.fromM < cur.toM - _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s + 1}].fromM",
                        RuleCode.SEGMENT_OVERLAP,
                        f"segment {s + 1} (starts {nxt.fromM}) overlaps segment {s} "
                        f"(ends {cur.toM})",
                    )
                )
        last = segs[-1]
        if not approx_equal(last.toM, float(block.distanceM)):
            issues.append(
                _err(
                    f"blocks[{b}].segments[{len(segs) - 1}].toM",
                    RuleCode.SEGMENT_END_NOT_BLOCK_DISTANCE,
                    f"last segment must end at block distance {block.distanceM}, got {last.toM}",
                )
            )
    return issues


# --------------------------------------------------------------------------- RULE-002
def rule_002_pool_length_multiple(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    pool = workout.poolLengthM
    boundary_sev = IssueSeverity.ERROR if ctx.strictSegmentBoundaryMode else IssueSeverity.WARNING
    for b, block in enumerate(workout.blocks):
        if block.distanceM % pool != 0:
            issues.append(
                _err(
                    f"blocks[{b}].distanceM",
                    RuleCode.DISTANCE_NOT_MULTIPLE_OF_POOL,
                    f"block distance {block.distanceM} is not a multiple of pool length {pool}",
                )
            )
        for s, seg in enumerate(block.segments):
            if not _is_wall_multiple(seg.toM, pool):
                issues.append(
                    _issue(
                        f"blocks[{b}].segments[{s}].toM",
                        RuleCode.SEGMENT_BOUNDARY_NOT_AT_WALL,
                        f"segment boundary {seg.toM} does not land on a wall (multiple of {pool})",
                        boundary_sev,
                    )
                )
    return issues


def _is_wall_multiple(value: float, pool: int) -> bool:
    ratio = value / pool
    return approx_equal(ratio, round(ratio))


# --------------------------------------------------------------------------- RULE-003
def rule_003_pace_bounds_direction(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        adaptation = block.adaptation
        if adaptation is None:
            continue
        fastest = adaptation.fastestAllowedPaceSecPer100M
        slowest = adaptation.slowestAllowedPaceSecPer100M
        for s, seg in enumerate(block.segments):
            target = seg.targetPaceSecPer100M
            if fastest is not None and target < fastest - _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s}].targetPaceSecPer100M",
                        RuleCode.TARGET_FASTER_THAN_FASTEST_ALLOWED,
                        f"target pace {target}, fastest allowed pace {fastest} "
                        "değerinden daha hızlı olamaz (smaller sec/100m = faster)",
                    )
                )
            if slowest is not None and target > slowest + _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s}].targetPaceSecPer100M",
                        RuleCode.TARGET_SLOWER_THAN_SLOWEST_ALLOWED,
                        f"target pace {target}, slowest allowed pace {slowest} "
                        "değerinden daha yavaş olamaz (larger sec/100m = slower)",
                    )
                )
    return issues


# --------------------------------------------------------------------------- RULE-004
def rule_004_progressive_mode(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        for s, seg in enumerate(block.segments):
            path = f"blocks[{b}].segments[{s}].endPaceSecPer100M"
            if seg.mode is PaceMode.progressive:
                if seg.endPaceSecPer100M is None:
                    issues.append(
                        _err(
                            path,
                            RuleCode.PROGRESSIVE_REQUIRES_END_PACE,
                            "progressive segment requires endPaceSecPer100M",
                        )
                    )
                elif seg.endPaceSecPer100M > seg.targetPaceSecPer100M + _TOL:
                    issues.append(
                        _err(
                            path,
                            RuleCode.PROGRESSIVE_END_NOT_FASTER,
                            f"progressive endPace {seg.endPaceSecPer100M} must be "
                            f"<= target {seg.targetPaceSecPer100M} (end at least as fast)",
                        )
                    )
            elif seg.endPaceSecPer100M is not None:
                issues.append(
                    _err(
                        path,
                        RuleCode.END_PACE_ONLY_FOR_PROGRESSIVE,
                        f"endPaceSecPer100M is only valid for progressive mode "
                        f"(mode={seg.mode.value})",
                    )
                )
    return issues


# --------------------------------------------------------------------------- RULE-005
def rule_005_adaptation_bounds_consistency(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        adaptation = block.adaptation
        if adaptation is None:
            continue
        fastest = adaptation.fastestAllowedPaceSecPer100M
        slowest = adaptation.slowestAllowedPaceSecPer100M
        base = f"blocks[{b}].adaptation"

        if adaptation.mode is AdaptationMode.off:
            if (
                fastest is not None
                or slowest is not None
                or adaptation.maxChangePercentPerLength is not None
            ):
                issues.append(
                    _warn(
                        base,
                        RuleCode.ADAPTATION_OFF_REDUNDANT_FIELDS,
                        "adaptation is off but bounds/max-change fields are set (ignored)",
                    )
                )
            continue

        if fastest is not None and slowest is not None:
            if fastest > slowest + _TOL:
                issues.append(
                    _err(
                        f"{base}.fastestAllowedPaceSecPer100M",
                        RuleCode.ADAPTATION_BOUNDS_REVERSED,
                        f"fastestAllowedPace {fastest} must be < slowestAllowedPace {slowest}",
                    )
                )
            elif approx_equal(fastest, slowest):
                issues.append(
                    _warn(
                        base,
                        RuleCode.ADAPTATION_BOUNDS_NO_ROOM,
                        "adaptation bounds leave no room to move",
                    )
                )

        if adaptation.mode is AdaptationMode.bounded_auto:
            missing = [
                name
                for name, value in (
                    ("maxChangePercentPerLength", adaptation.maxChangePercentPerLength),
                    ("fastestAllowedPaceSecPer100M", fastest),
                    ("slowestAllowedPaceSecPer100M", slowest),
                )
                if value is None
            ]
            if missing:
                issues.append(
                    _err(
                        base,
                        RuleCode.BOUNDED_AUTO_MISSING_FIELDS,
                        f"bounded_auto requires: {', '.join(missing)}",
                    )
                )
    return issues


# --------------------------------------------------------------------------- RULE-006
#: Feedback flag (contract) -> typed capability.
_FEEDBACK_FLAG_TO_CAPABILITY = {
    "showGhost": FeedbackCapability.SHOW_GHOST,
    "showGapAtWall": FeedbackCapability.SHOW_GAP_AT_WALL,
    "showContinuousGap": FeedbackCapability.SHOW_CONTINUOUS_GAP,
}
#: Essential capabilities error out when unsupported; the rest can fall back → WARNING.
_ESSENTIAL_CAPABILITIES = frozenset({FeedbackCapability.SHOW_GHOST})


def rule_006_feedback_capability(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        fb = block.feedback
        if fb is None:
            continue
        for flag, capability in _FEEDBACK_FLAG_TO_CAPABILITY.items():
            if not getattr(fb, flag):
                continue
            path = f"blocks[{b}].feedback.{flag}"
            if not has_context:
                # No context: we cannot confirm the target supports this — warn, don't fail.
                issues.append(
                    _warn(
                        path,
                        RuleCode.FEEDBACK_CAPABILITY_NOT_VERIFIED,
                        f"feedback capability {capability.value} cannot be verified "
                        "without a validation context",
                    )
                )
            elif capability not in ctx.supportedFeedbackCapabilities:
                sev = (
                    IssueSeverity.ERROR
                    if capability in _ESSENTIAL_CAPABILITIES
                    else IssueSeverity.WARNING
                )
                issues.append(
                    _issue(
                        path,
                        RuleCode.UNSUPPORTED_FEEDBACK_CAPABILITY,
                        f"feedback capability {capability.value} is not supported by the target",
                        sev,
                    )
                )
    return issues


# --------------------------------------------------------------------------- RULE-007
def rule_007_total_distance(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    total = sum(block.repetitions * block.distanceM for block in workout.blocks)
    issues: list[ValidationIssue] = []
    if total <= 0:
        issues.append(
            _err(
                "totalDistanceM",
                RuleCode.TOTAL_DISTANCE_NON_POSITIVE,
                "total workout distance must be positive",
            )
        )
    if ctx.maxTotalWorkoutDistanceM is not None and total > ctx.maxTotalWorkoutDistanceM:
        issues.append(
            _err(
                "totalDistanceM",
                RuleCode.TOTAL_DISTANCE_EXCEEDS_MAX,
                f"total distance {total} exceeds maximum {ctx.maxTotalWorkoutDistanceM}",
            )
        )
    return issues


# --------------------------------------------------------------------------- RULE-008
def rule_008_ghost_source_references(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        gs = block.ghostSource
        if gs is None:
            continue
        gtype = getattr(gs, "type", None)
        if gtype in ("personal_best", "past_session"):
            ref = gs.referenceSessionId  # type: ignore[union-attr]
            issues.extend(
                _reference_issue(b, "referenceSessionId", ref, ctx.completedSessionIds, has_context)
            )
        elif gtype == "coach_benchmark":
            ref = gs.profileRef  # type: ignore[union-attr]
            issues.extend(
                _reference_issue(
                    b, "profileRef", ref, ctx.knownCoachBenchmarkProfileRefs, has_context
                )
            )
    return issues


def _reference_issue(
    b: int, field: str, ref: str, known: frozenset[str], has_context: bool
) -> list[ValidationIssue]:
    if not has_context:
        return [
            _warn(
                f"blocks[{b}].ghostSource.{field}",
                RuleCode.REFERENCE_NOT_VERIFIED,
                f"{field} '{ref}' cannot be verified without a validation context",
            )
        ]
    if ref not in known:
        return [
            _err(
                f"blocks[{b}].ghostSource.{field}",
                RuleCode.REFERENCE_NOT_FOUND,
                f"{field} '{ref}' is not a known reference",
            )
        ]
    return []


# --------------------------------------------------------------------------- RULE-009
def rule_009_rest_interval_sanity(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        if not isinstance(block.rest, RestInterval):
            continue
        active = _estimate_active_duration_sec(block)
        margin = block.rest.startIntervalSec - active
        path = f"blocks[{b}].rest.startIntervalSec"
        if margin <= _TOL:
            issues.append(
                _err(
                    path,
                    RuleCode.REST_INTERVAL_NEGATIVE,
                    f"interval {block.rest.startIntervalSec}s leaves no rest: estimated "
                    f"active swim is {active:.2f}s",
                )
            )
        elif margin < _TIGHT_REST_MARGIN_SEC:
            issues.append(
                _warn(
                    path,
                    RuleCode.REST_INTERVAL_TIGHT,
                    f"interval leaves only {margin:.2f}s rest over estimated active "
                    f"swim {active:.2f}s",
                )
            )
    return issues


def _estimate_active_duration_sec(block: RepeatBlock) -> float:
    """Small, isolated estimate — replaced by Commit 4 pace math later.

    even/controlled/negative: distance * targetPace / 100.
    progressive: distance * mean(target, end) / 100.
    """
    total = 0.0
    for seg in block.segments:
        total += _segment_duration_sec(seg)
    return total


def _segment_duration_sec(seg: PaceSegment) -> float:
    distance = seg.toM - seg.fromM
    if seg.mode is PaceMode.progressive and seg.endPaceSecPer100M is not None:
        pace = (seg.targetPaceSecPer100M + seg.endPaceSecPer100M) / 2.0
    elif seg.mode is PaceMode.controlled_start and seg.startPaceSecPer100M is not None:
        pace = (seg.startPaceSecPer100M + seg.targetPaceSecPer100M) / 2.0
    else:
        pace = seg.targetPaceSecPer100M
    return distance * pace / 100.0


# --------------------------------------------------------------------------- RULE-010
def rule_010_schema_version(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    if workout.schemaVersion not in ctx.supportedSchemaVersions:
        return [
            _err(
                "schemaVersion",
                RuleCode.UNSUPPORTED_SCHEMA_VERSION,
                f"schema version {workout.schemaVersion} is not supported "
                f"(supported: {sorted(ctx.supportedSchemaVersions)})",
            )
        ]
    return []


# --------------------------------------------------------------------------- RULE-011
def rule_011_controlled_start(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        for s, seg in enumerate(block.segments):
            path = f"blocks[{b}].segments[{s}].startPaceSecPer100M"
            if seg.mode is PaceMode.controlled_start:
                if seg.startPaceSecPer100M is None:
                    issues.append(
                        _err(
                            path,
                            RuleCode.CONTROLLED_START_PACE_REQUIRED,
                            "controlled_start segment requires startPaceSecPer100M",
                        )
                    )
                elif seg.startPaceSecPer100M < seg.targetPaceSecPer100M - _TOL:
                    # start must be slower-or-equal (numerically >=) than target
                    issues.append(
                        _err(
                            path,
                            RuleCode.CONTROLLED_START_DIRECTION_INVALID,
                            f"controlled_start startPace {seg.startPaceSecPer100M} must be "
                            f">= target {seg.targetPaceSecPer100M} (start no faster than target)",
                        )
                    )
            elif seg.startPaceSecPer100M is not None:
                issues.append(
                    _err(
                        path,
                        RuleCode.START_PACE_NOT_ALLOWED_FOR_MODE,
                        f"startPaceSecPer100M is only valid for controlled_start "
                        f"(mode={seg.mode.value})",
                    )
                )
    return issues


# --------------------------------------------------------------------------- RULE-012
def _segment_terminal_pace(seg: PaceSegment) -> float:
    """Terminal (exit) pace of a segment: end pace for progressive, else target."""
    if seg.mode is PaceMode.progressive and seg.endPaceSecPer100M is not None:
        return seg.endPaceSecPer100M
    return seg.targetPaceSecPer100M


def rule_012_negative_split_order(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    """Negative-split ordering.

    The FIRST ``negative_split_part`` must be no slower than the terminal pace of the
    preceding (normal/progressive) segment; consecutive negative-split parts may not get
    slower (numerically larger) than the previous part.
    """
    issues: list[ValidationIssue] = []
    for b, block in enumerate(workout.blocks):
        prev_ns_pace: float | None = None
        prev_ns_index: int | None = None
        prev_terminal: float | None = None
        prev_terminal_index: int | None = None
        for s, seg in enumerate(block.segments):
            if seg.mode is not PaceMode.negative_split_part:
                prev_terminal = _segment_terminal_pace(seg)
                prev_terminal_index = s
                continue
            # first negative-split part vs the previous segment's terminal pace
            if (
                prev_ns_pace is None
                and prev_terminal is not None
                and seg.targetPaceSecPer100M > prev_terminal + _TOL
            ):
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s}].targetPaceSecPer100M",
                        RuleCode.NEGATIVE_SPLIT_ORDER_INVALID,
                        f"first negative-split segment {s} ({seg.targetPaceSecPer100M}) is "
                        f"slower than the terminal pace of segment {prev_terminal_index} "
                        f"({prev_terminal}); a negative split must not start slower",
                    )
                )
            if prev_ns_pace is not None and seg.targetPaceSecPer100M > prev_ns_pace + _TOL:
                issues.append(
                    _err(
                        f"blocks[{b}].segments[{s}].targetPaceSecPer100M",
                        RuleCode.NEGATIVE_SPLIT_ORDER_INVALID,
                        f"negative-split segment {s} ({seg.targetPaceSecPer100M}) is slower "
                        f"than segment {prev_ns_index} ({prev_ns_pace}); later parts must "
                        f"not slow down",
                    )
                )
            prev_ns_pace = seg.targetPaceSecPer100M
            prev_ns_index = s
    return issues


# --------------------------------------------------------------------------- RULE-013 (Workout 1.1)
def rule_013_start_mode_and_overrides(
    workout: AnyWorkoutTemplate,
    ctx: WorkoutValidationContext,
    has_context: bool,
) -> list[ValidationIssue]:
    """Workout 1.1 start-mode / repeat-override semantics.

    A 1.0 workout has no start policy, so this rule is a no-op for it. For 1.1 it checks that
    every repeat override targets a valid repeat index and respects the start policy. The
    pydantic model already enforces most of this at construction; this rule surfaces the same
    problems as machine-readable ``ValidationIssue`` objects for the validation report.
    """
    issues: list[ValidationIssue] = []
    start_policy = getattr(workout, "startPolicy", None)
    if start_policy is None:
        return issues  # 1.0 workout: nothing to check
    overrides = getattr(workout, "repeatOverrides", []) or []
    blocks = workout.blocks
    max_reps = max((b.repetitions for b in blocks), default=0)
    seen: set[int] = set()
    for ov in overrides:
        if ov.repeatIndex in seen or not (0 <= ov.repeatIndex < max_reps):
            issues.append(
                _err(
                    f"repeatOverrides[{ov.repeatIndex}]",
                    RuleCode.REPEAT_OVERRIDE_INDEX_INVALID,
                    f"repeatIndex {ov.repeatIndex} is duplicate or out of range [0,{max_reps})",
                )
            )
        seen.add(ov.repeatIndex)
        if ov.startMode is not None and not start_policy.allowRepeatOverride:
            issues.append(
                _err(
                    f"repeatOverrides[{ov.repeatIndex}].startMode",
                    RuleCode.START_OVERRIDE_NOT_ALLOWED,
                    "repeat override sets startMode but startPolicy.allowRepeatOverride is false",
                )
            )
    for b, block in enumerate(blocks):
        if getattr(block, "startMode", None) is not None and not start_policy.allowBlockOverride:
            issues.append(
                _err(
                    f"blocks[{b}].startMode",
                    RuleCode.START_OVERRIDE_NOT_ALLOWED,
                    "block sets startMode but startPolicy.allowBlockOverride is false",
                )
            )
    return issues
