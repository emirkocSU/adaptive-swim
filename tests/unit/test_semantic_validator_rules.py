"""Commit 3 semantic validator — per-rule scenarios (B6).

Each rule has at least one valid and one invalid case (plus boundary cases where
relevant). File-based semantic goldens are also cross-checked against the expected code.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from contracts.enums import IssueSeverity
from contracts.workout import WorkoutTemplateVersion
from swimcore.workout import (
    RuleCode,
    WorkoutValidationContext,
    validate_workout,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_DIR = REPO_ROOT / "src" / "contracts" / "examples" / "semantic_invalid"


# --------------------------------------------------------------------------- builders
def _segment(fromM: float, toM: float, mode: str = "even_pace", **extra: object) -> dict:
    seg: dict[str, object] = {
        "fromM": fromM,
        "toM": toM,
        "mode": mode,
        "targetPaceSecPer100M": 83.0,
    }
    seg.update(extra)
    return seg


def _block(distanceM: int = 100, repetitions: int = 1, **extra: object) -> dict:
    block: dict[str, object] = {
        "type": "repeat",
        "repetitions": repetitions,
        "distanceM": distanceM,
        "rest": {"type": "none"},
        "segments": [_segment(0, distanceM)],
    }
    block.update(extra)
    return block


def _workout(blocks: list[dict] | None = None, **extra: object) -> WorkoutTemplateVersion:
    doc: dict[str, object] = {
        "schemaVersion": "1.0",
        "name": "wk",
        "poolLengthM": 25,
        "stroke": "freestyle",
        "blocks": blocks if blocks is not None else [_block()],
    }
    doc.update(extra)
    return WorkoutTemplateVersion.model_validate(doc)


def _codes(
    workout: WorkoutTemplateVersion, ctx: WorkoutValidationContext | None = None
) -> set[str]:
    return {i.rule for i in validate_workout(workout, ctx).issues}


CTX = WorkoutValidationContext()


# --------------------------------------------------------------------------- RULE-001
def test_valid_contiguous_coverage() -> None:
    w = _workout([_block(200, segments=[_segment(0, 100), _segment(100, 200)])])
    assert validate_workout(w, CTX).isValid


def test_gap_between_segments() -> None:
    w = _workout([_block(200, segments=[_segment(0, 50), _segment(100, 200)])])
    assert RuleCode.SEGMENT_GAP in _codes(w, CTX)


def test_segment_overlap() -> None:
    w = _workout([_block(100, segments=[_segment(0, 75), _segment(50, 100)])])
    assert RuleCode.SEGMENT_OVERLAP in _codes(w, CTX)


def test_first_segment_not_zero() -> None:
    w = _workout([_block(100, segments=[_segment(25, 100)])])
    assert RuleCode.SEGMENT_START_NOT_ZERO in _codes(w, CTX)


def test_last_segment_not_block_distance() -> None:
    w = _workout([_block(100, segments=[_segment(0, 75)])])
    assert RuleCode.SEGMENT_END_NOT_BLOCK_DISTANCE in _codes(w, CTX)


# --------------------------------------------------------------------------- RULE-002
def test_distance_not_multiple_of_pool() -> None:
    w = _workout([_block(75, segments=[_segment(0, 75)])], poolLengthM=50)
    assert RuleCode.DISTANCE_NOT_MULTIPLE_OF_POOL in _codes(w, CTX)


def test_segment_boundary_not_at_wall_warning_mode() -> None:
    # 30m boundary in a 25m pool: not on a wall → WARNING (non-strict).
    w = _workout(
        [_block(100, segments=[_segment(0, 30), _segment(30, 100)])],
        poolLengthM=25,
    )
    result = validate_workout(w, WorkoutValidationContext(strictSegmentBoundaryMode=False))
    wall = [i for i in result.issues if i.rule == RuleCode.SEGMENT_BOUNDARY_NOT_AT_WALL]
    assert wall and all(i.severity is IssueSeverity.WARNING for i in wall)
    assert result.isValid  # a warning does not invalidate


def test_segment_boundary_not_at_wall_strict_error_mode() -> None:
    w = _workout(
        [_block(100, segments=[_segment(0, 30), _segment(30, 100)])],
        poolLengthM=25,
    )
    result = validate_workout(w, WorkoutValidationContext(strictSegmentBoundaryMode=True))
    wall = [i for i in result.issues if i.rule == RuleCode.SEGMENT_BOUNDARY_NOT_AT_WALL]
    assert wall and all(i.severity is IssueSeverity.ERROR for i in wall)
    assert not result.isValid


# --------------------------------------------------------------------------- RULE-003
def _adaptation(**extra: object) -> dict:
    ad: dict[str, object] = {"mode": "bounded_auto", "maxChangePercentPerLength": 1.0}
    ad.update(extra)
    return ad


def test_target_faster_than_fastest_allowed() -> None:
    block = _block(
        100,
        segments=[_segment(0, 100, targetPaceSecPer100M=76.0)],
        adaptation=_adaptation(
            fastestAllowedPaceSecPer100M=78.0, slowestAllowedPaceSecPer100M=90.0
        ),
    )
    assert RuleCode.TARGET_FASTER_THAN_FASTEST_ALLOWED in _codes(_workout([block]), CTX)


def test_target_slower_than_slowest_allowed() -> None:
    block = _block(
        100,
        segments=[_segment(0, 100, targetPaceSecPer100M=95.0)],
        adaptation=_adaptation(
            fastestAllowedPaceSecPer100M=78.0, slowestAllowedPaceSecPer100M=90.0
        ),
    )
    assert RuleCode.TARGET_SLOWER_THAN_SLOWEST_ALLOWED in _codes(_workout([block]), CTX)


def test_pace_within_bounds_is_valid() -> None:
    block = _block(
        100,
        segments=[_segment(0, 100, targetPaceSecPer100M=83.0)],
        adaptation=_adaptation(
            fastestAllowedPaceSecPer100M=78.0, slowestAllowedPaceSecPer100M=90.0
        ),
    )
    assert validate_workout(_workout([block]), CTX).isValid


# --------------------------------------------------------------------------- RULE-004
def test_valid_progressive_pace() -> None:
    block = _block(
        100,
        segments=[_segment(0, 100, mode="progressive", endPaceSecPer100M=80.0)],
    )
    assert validate_workout(_workout([block]), CTX).isValid


def test_progressive_without_end_pace() -> None:
    block = _block(100, segments=[_segment(0, 100, mode="progressive")])
    assert RuleCode.PROGRESSIVE_REQUIRES_END_PACE in _codes(_workout([block]), CTX)


def test_progressive_becoming_slower() -> None:
    block = _block(
        100,
        segments=[_segment(0, 100, mode="progressive", endPaceSecPer100M=88.0)],
    )
    assert RuleCode.PROGRESSIVE_END_NOT_FASTER in _codes(_workout([block]), CTX)


def test_end_pace_supplied_in_even_mode() -> None:
    block = _block(100, segments=[_segment(0, 100, endPaceSecPer100M=80.0)])
    assert RuleCode.END_PACE_ONLY_FOR_PROGRESSIVE in _codes(_workout([block]), CTX)


# --------------------------------------------------------------------------- RULE-005
def test_fastest_bound_greater_than_slowest() -> None:
    block = _block(
        100,
        adaptation=_adaptation(
            fastestAllowedPaceSecPer100M=90.0, slowestAllowedPaceSecPer100M=80.0
        ),
    )
    assert RuleCode.ADAPTATION_BOUNDS_REVERSED in _codes(_workout([block]), CTX)


def test_bounded_auto_missing_required_fields() -> None:
    block = _block(100, adaptation={"mode": "bounded_auto"})
    assert RuleCode.BOUNDED_AUTO_MISSING_FIELDS in _codes(_workout([block]), CTX)


def test_adaptation_off_with_redundant_fields_warning() -> None:
    block = _block(
        100,
        adaptation={"mode": "off", "fastestAllowedPaceSecPer100M": 78.0},
    )
    result = validate_workout(_workout([block]), CTX)
    redundant = [i for i in result.issues if i.rule == RuleCode.ADAPTATION_OFF_REDUNDANT_FIELDS]
    assert redundant and all(i.severity is IssueSeverity.WARNING for i in redundant)
    assert result.isValid


def test_adaptation_bounds_no_room_warning() -> None:
    block = _block(
        100,
        adaptation=_adaptation(
            fastestAllowedPaceSecPer100M=83.0, slowestAllowedPaceSecPer100M=83.0
        ),
    )
    result = validate_workout(_workout([block]), CTX)
    assert any(i.rule == RuleCode.ADAPTATION_BOUNDS_NO_ROOM for i in result.warnings)


# --------------------------------------------------------------------------- RULE-006
def test_unsupported_continuous_feedback_capability() -> None:
    block = _block(100, feedback={"showGhost": True, "showContinuousGap": True})
    ctx = WorkoutValidationContext(
        supportedFeedbackCapabilities=frozenset({"showGhost", "showGapAtWall"})
    )
    result = validate_workout(_workout([block]), ctx)
    hits = [i for i in result.issues if i.rule == RuleCode.FEEDBACK_CAPABILITY_UNSUPPORTED]
    assert hits and any("showContinuousGap" in i.path for i in hits)


def test_supported_feedback_capability_is_valid() -> None:
    block = _block(100, feedback={"showGhost": True, "showGapAtWall": True})
    ctx = WorkoutValidationContext(
        supportedFeedbackCapabilities=frozenset({"showGhost", "showGapAtWall"})
    )
    assert validate_workout(_workout([block]), ctx).isValid


# --------------------------------------------------------------------------- RULE-007
def test_total_workout_distance_calculation() -> None:
    w = _workout([_block(100, repetitions=10)])  # 1000 m
    ctx = WorkoutValidationContext(maxTotalWorkoutDistanceM=2000)
    assert validate_workout(w, ctx).isValid


def test_maximum_total_distance_exceeded() -> None:
    w = _workout([_block(100, repetitions=10)])  # 1000 m
    ctx = WorkoutValidationContext(maxTotalWorkoutDistanceM=500)
    assert RuleCode.TOTAL_DISTANCE_EXCEEDS_MAX in _codes(w, ctx)


# --------------------------------------------------------------------------- RULE-008
def _ghost_block(**gs: object) -> dict:
    return _block(100, ghostSource=gs)


def test_valid_completed_session_ghost_reference() -> None:
    block = _ghost_block(type="past_session", referenceSessionId="sess-1")
    ctx = WorkoutValidationContext(completedSessionIds=frozenset({"sess-1"}))
    assert validate_workout(_workout([block]), ctx).isValid


def test_missing_completed_session_reference() -> None:
    block = _ghost_block(type="past_session", referenceSessionId="sess-x")
    ctx = WorkoutValidationContext(completedSessionIds=frozenset({"sess-1"}))
    assert RuleCode.REFERENCE_NOT_FOUND in _codes(_workout([block]), ctx)


def test_reference_cannot_be_verified_without_context() -> None:
    block = _ghost_block(type="past_session", referenceSessionId="sess-x")
    result = validate_workout(_workout([block]), None)  # no context
    assert any(i.rule == RuleCode.REFERENCE_NOT_VERIFIED for i in result.warnings)
    assert result.isValid  # a warning does not invalidate


# --------------------------------------------------------------------------- RULE-009
def test_interval_with_valid_positive_rest() -> None:
    # 100 m @ 83 s/100 m ≈ 83 s active; interval 120 s → 37 s rest.
    block = _block(100, rest={"type": "interval", "startIntervalSec": 120})
    assert validate_workout(_workout([block]), CTX).isValid


def test_interval_producing_negative_rest() -> None:
    block = _block(100, rest={"type": "interval", "startIntervalSec": 30})
    assert RuleCode.REST_INTERVAL_NEGATIVE in _codes(_workout([block]), CTX)


def test_interval_tight_rest_warning() -> None:
    # active ≈ 83 s; interval 84 s → 1 s rest → tight (WARNING).
    block = _block(100, rest={"type": "interval", "startIntervalSec": 84})
    result = validate_workout(_workout([block]), CTX)
    assert any(i.rule == RuleCode.REST_INTERVAL_TIGHT for i in result.warnings)
    assert result.isValid


# --------------------------------------------------------------------------- RULE-010
def test_supported_schema_version() -> None:
    w = _workout()
    ctx = WorkoutValidationContext(supportedSchemaVersions=frozenset({"1.0"}))
    assert RuleCode.UNSUPPORTED_SCHEMA_VERSION not in _codes(w, ctx)


def test_unsupported_schema_version() -> None:
    w = _workout()
    ctx = WorkoutValidationContext(supportedSchemaVersions=frozenset({"2.0"}))
    assert RuleCode.UNSUPPORTED_SCHEMA_VERSION in _codes(w, ctx)


# --------------------------------------------------------------------------- result semantics
def test_multiple_issues_returned_in_deterministic_order() -> None:
    # Two blocks, each with a defect; ordering must be stable across runs.
    w = _workout(
        [
            _block(200, segments=[_segment(0, 50), _segment(100, 200)]),  # gap in block 0
            _block(100, segments=[_segment(25, 100)]),  # start-not-zero in block 1
        ]
    )
    r1 = validate_workout(w, CTX)
    r2 = validate_workout(w, CTX)
    order1 = [(i.path, i.rule) for i in r1.issues]
    order2 = [(i.path, i.rule) for i in r2.issues]
    assert order1 == order2
    # block 0 issues sort before block 1 issues.
    assert order1[0][0].startswith("blocks[0]")


def test_warnings_do_not_invalidate_workout() -> None:
    block = _block(100, rest={"type": "interval", "startIntervalSec": 84})  # tight → warning
    result = validate_workout(_workout([block]), CTX)
    assert result.warnings and result.isValid


def test_errors_invalidate_workout() -> None:
    w = _workout([_block(100, segments=[_segment(0, 75)])])  # last not block distance
    result = validate_workout(w, CTX)
    assert result.errors and not result.isValid


def test_validator_does_not_mutate_input() -> None:
    w = _workout([_block(200, segments=[_segment(0, 50), _segment(100, 200)])])
    before = w.model_dump()
    validate_workout(w, CTX)
    assert w.model_dump() == before


def test_validator_performs_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("validator must not open files")

    monkeypatch.setattr(builtins, "open", _boom)
    w = _workout()
    validate_workout(w, CTX)  # must not touch the filesystem


def test_no_duplicate_issues() -> None:
    w = _workout([_block(200, segments=[_segment(0, 50), _segment(100, 200)])])
    issues = validate_workout(w, CTX).issues
    keys = [(i.path, i.rule, i.message) for i in issues]
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------- file goldens
_EXPECTED_FILE_CODE = {
    "gap_in_segments": RuleCode.SEGMENT_GAP,
    "segment_overlap": RuleCode.SEGMENT_OVERLAP,
    "first_segment_not_zero": RuleCode.SEGMENT_START_NOT_ZERO,
    "last_segment_not_block_distance": RuleCode.SEGMENT_END_NOT_BLOCK_DISTANCE,
    "distance_not_multiple_of_pool": RuleCode.DISTANCE_NOT_MULTIPLE_OF_POOL,
    "target_faster_than_fastest_allowed": RuleCode.TARGET_FASTER_THAN_FASTEST_ALLOWED,
    "target_slower_than_slowest_allowed": RuleCode.TARGET_SLOWER_THAN_SLOWEST_ALLOWED,
    "progressive_without_end_pace": RuleCode.PROGRESSIVE_REQUIRES_END_PACE,
    "progressive_becoming_slower": RuleCode.PROGRESSIVE_END_NOT_FASTER,
    "end_pace_in_even_mode": RuleCode.END_PACE_ONLY_FOR_PROGRESSIVE,
    "adaptation_bounds_reversed": RuleCode.ADAPTATION_BOUNDS_REVERSED,
    "bounded_auto_missing_fields": RuleCode.BOUNDED_AUTO_MISSING_FIELDS,
    "interval_negative_rest": RuleCode.REST_INTERVAL_NEGATIVE,
}


@pytest.mark.parametrize(
    "path",
    sorted(SEMANTIC_DIR.glob("*.json")),
    ids=lambda p: p.name,
)
def test_semantic_golden_flagged_with_expected_rule(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    workout = WorkoutTemplateVersion.model_validate(copy.deepcopy(doc))
    result = validate_workout(workout, CTX)
    expected = _EXPECTED_FILE_CODE[path.stem]
    assert not result.isValid
    assert expected in {i.rule for i in result.issues}
