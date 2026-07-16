"""Pure, deterministic semantic workout validation layer (Commit 3).

No I/O, no DB, no network, no global state. All external facts arrive via an injected
``WorkoutValidationContext``. JSON Schema handles *structural* validation; this layer
handles *semantic* rules and returns machine-readable ``ValidationIssue`` objects.
"""

from contracts.errors import ValidationIssue
from swimcore.workout.context import WorkoutValidationContext
from swimcore.workout.validator import (
    RuleCode,
    WorkoutValidationResult,
    validate_workout,
)

__all__ = [
    "RuleCode",
    "ValidationIssue",
    "WorkoutValidationContext",
    "WorkoutValidationResult",
    "validate_workout",
]
