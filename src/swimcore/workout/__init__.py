"""Pure, deterministic semantic workout validation layer (Commit 3).

No I/O, no DB, no network, no global state. All external facts arrive via an injected
``WorkoutValidationContext``. JSON Schema handles *structural* validation; this layer
handles *semantic* rules and returns machine-readable ``ValidationIssue`` objects.
"""

from contracts.errors import ValidationIssue
from swimcore.workout.context import WorkoutValidationContext
from swimcore.workout.migrations import migrate_workout_1_0_to_1_1
from swimcore.workout.profile_rules import validate_approved_pace_profile
from swimcore.workout.start_mode import (
    StartModeResolutionError,
    resolve_default_start_mode,
    resolve_repeat_start_mode,
)
from swimcore.workout.validator import (
    RuleCode,
    WorkoutValidationResult,
    validate_workout,
)

__all__ = [
    "RuleCode",
    "StartModeResolutionError",
    "ValidationIssue",
    "WorkoutValidationContext",
    "WorkoutValidationResult",
    "migrate_workout_1_0_to_1_1",
    "resolve_default_start_mode",
    "resolve_repeat_start_mode",
    "validate_approved_pace_profile",
    "validate_workout",
]
