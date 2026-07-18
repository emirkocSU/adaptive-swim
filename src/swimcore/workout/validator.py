"""Semantic workout validator (pure, deterministic).

``validate_workout`` runs every rule, collects all issues in one pass (never stops at the
first error), returns a ``WorkoutValidationResult``, and never mutates the input. Rules
raise no exceptions for domain problems — they return ``ValidationIssue`` objects. Only
genuine programming errors may surface as exceptions.

Issue ordering is deterministic: (block index, segment index, rule code).
"""

from __future__ import annotations

from contracts._base import StrictModel
from contracts.enums import IssueSeverity
from contracts.errors import ValidationIssue
from contracts.workout import AnyWorkoutTemplate
from swimcore.workout import rules
from swimcore.workout.context import WorkoutValidationContext
from swimcore.workout.rules import RuleCode

__all__ = ["RuleCode", "WorkoutValidationResult", "validate_workout"]


class WorkoutValidationResult(StrictModel):
    issues: list[ValidationIssue]
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    isValid: bool


# Rules that operate per block/segment, in declaration order. Each returns a list of issues.
_ALL_RULES = (
    rules.rule_001_contiguous_coverage,
    rules.rule_002_pool_length_multiple,
    rules.rule_003_pace_bounds_direction,
    rules.rule_004_progressive_mode,
    rules.rule_005_adaptation_bounds_consistency,
    rules.rule_006_feedback_capability,
    rules.rule_007_total_distance,
    rules.rule_008_ghost_source_references,
    rules.rule_009_rest_interval_sanity,
    rules.rule_010_schema_version,
    rules.rule_011_controlled_start,
    rules.rule_012_negative_split_order,
    rules.rule_013_start_mode_and_overrides,
)


def _sort_key(issue: ValidationIssue) -> tuple[int, int, str]:
    return (_block_index(issue.path), _segment_index(issue.path), issue.rule)


def _block_index(path: str) -> int:
    # paths look like "blocks[2].segments[1].fromM"; missing -> -1 so root issues sort first.
    return _bracket_index(path, "blocks")


def _segment_index(path: str) -> int:
    return _bracket_index(path, "segments")


def _bracket_index(path: str, token: str) -> int:
    marker = f"{token}["
    start = path.find(marker)
    if start == -1:
        return -1
    start += len(marker)
    end = path.find("]", start)
    if end == -1:
        return -1
    try:
        return int(path[start:end])
    except ValueError:
        return -1


def validate_workout(
    workout: AnyWorkoutTemplate,
    context: WorkoutValidationContext | None = None,
) -> WorkoutValidationResult:
    """Validate a structurally-valid workout against the semantic rules.

    Pure and deterministic. Does not mutate ``workout``. When ``context`` is ``None`` a
    default context is used and context-dependent rules degrade to WARNINGs.
    """
    ctx = context if context is not None else WorkoutValidationContext()
    has_context = context is not None

    issues: list[ValidationIssue] = []
    for rule in _ALL_RULES:
        issues.extend(rule(workout, ctx, has_context))

    # Deduplicate identical issues (same path+rule+message) while preserving order.
    seen: set[tuple[str, str, str]] = set()
    unique: list[ValidationIssue] = []
    for issue in issues:
        key = (issue.path, issue.rule, issue.message)
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    unique.sort(key=_sort_key)
    errors = [i for i in unique if i.severity is IssueSeverity.ERROR]
    warnings = [i for i in unique if i.severity is IssueSeverity.WARNING]
    return WorkoutValidationResult(
        issues=unique,
        errors=errors,
        warnings=warnings,
        isValid=not errors,
    )
