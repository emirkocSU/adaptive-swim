"""Commit 3 — context behaviour, degradation without context, and migration registry."""

from __future__ import annotations

from contracts.workout import WorkoutTemplateVersion
from swimcore.workout import (
    RuleCode,
    WorkoutValidationContext,
    validate_workout,
)
from swimcore.workout.migrations import (
    CURRENT_SCHEMA_VERSION,
    has_migration_path,
    migrate,
)


def _workout(blocks: list[dict] | None = None, **extra: object) -> WorkoutTemplateVersion:
    doc: dict[str, object] = {
        "schemaVersion": "1.0",
        "name": "wk",
        "poolLengthM": 25,
        "stroke": "freestyle",
        "blocks": blocks
        or [
            {
                "type": "repeat",
                "repetitions": 1,
                "distanceM": 100,
                "rest": {"type": "none"},
                "segments": [
                    {"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 83.0}
                ],
            }
        ],
    }
    doc.update(extra)
    return WorkoutTemplateVersion.model_validate(doc)


# --------------------------------------------------------------------------- context defaults
def test_default_context_is_used_when_none() -> None:
    result = validate_workout(_workout(), None)
    assert result.isValid  # a clean workout is valid under the default context


def test_context_is_all_explicit_inputs() -> None:
    ctx = WorkoutValidationContext(
        supportedSchemaVersions=frozenset({"1.0"}),
        maxTotalWorkoutDistanceM=3000,
        completedSessionIds=frozenset({"s1"}),
        knownCoachBenchmarkProfileRefs=frozenset({"p1"}),
        supportedFeedbackCapabilities=frozenset({"showGhost"}),
        strictSegmentBoundaryMode=True,
    )
    assert ctx.maxTotalWorkoutDistanceM == 3000
    assert "s1" in ctx.completedSessionIds


# --------------------------------------------------------------------------- degradation
def test_reference_degrades_to_warning_without_context() -> None:
    block = {
        "type": "repeat",
        "repetitions": 1,
        "distanceM": 100,
        "rest": {"type": "none"},
        "segments": [{"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 83.0}],
        "ghostSource": {"type": "past_session", "referenceSessionId": "unknown"},
    }
    result = validate_workout(_workout([block]), None)
    assert any(i.rule == RuleCode.REFERENCE_NOT_VERIFIED for i in result.warnings)
    assert result.isValid


def test_reference_becomes_error_with_context_when_unknown() -> None:
    block = {
        "type": "repeat",
        "repetitions": 1,
        "distanceM": 100,
        "rest": {"type": "none"},
        "segments": [{"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 83.0}],
        "ghostSource": {"type": "past_session", "referenceSessionId": "unknown"},
    }
    ctx = WorkoutValidationContext(completedSessionIds=frozenset({"known"}))
    result = validate_workout(_workout([block]), ctx)
    assert any(i.rule == RuleCode.REFERENCE_NOT_FOUND for i in result.errors)
    assert not result.isValid


def test_coach_benchmark_reference_resolution() -> None:
    block = {
        "type": "repeat",
        "repetitions": 1,
        "distanceM": 100,
        "rest": {"type": "none"},
        "segments": [{"fromM": 0, "toM": 100, "mode": "even_pace", "targetPaceSecPer100M": 83.0}],
        "ghostSource": {"type": "coach_benchmark", "profileRef": "coach-A"},
    }
    ok = WorkoutValidationContext(knownCoachBenchmarkProfileRefs=frozenset({"coach-A"}))
    assert validate_workout(_workout([block]), ok).isValid
    bad = WorkoutValidationContext(knownCoachBenchmarkProfileRefs=frozenset({"coach-B"}))
    assert not validate_workout(_workout([block]), bad).isValid


# --------------------------------------------------------------------------- migrations
def test_noop_migration_path_exists() -> None:
    assert has_migration_path("1.0", "1.0")
    assert CURRENT_SCHEMA_VERSION == "1.0"


def test_noop_migration_returns_same_document() -> None:
    doc = {"schemaVersion": "1.0", "x": 1}
    assert migrate(doc, "1.0", "1.0") == doc


def test_unknown_migration_path_is_absent() -> None:
    assert not has_migration_path("0.9", "1.0")
    assert not has_migration_path("1.0", "2.0")
