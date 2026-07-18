"""Schema-version migration registry (pure functions).

The ``1.0 → 1.0`` no-op is registered for structural completeness. The ``1.0 → 1.1``
migration is *explicit*: the caller must supply the start mode — a legacy workout is never
silently assumed to be a dive or an in-water start.
"""

from __future__ import annotations

from collections.abc import Callable

from contracts.enums import StartMode, WorkoutGoal
from contracts.workout import (
    StartPolicy,
    WorkoutTemplateV1_0,
    WorkoutTemplateV1_1,
)

MigrationFn = Callable[[dict[str, object]], dict[str, object]]


def _noop_1_0(document: dict[str, object]) -> dict[str, object]:
    return document


#: (from_version, to_version) -> migration function.
MIGRATIONS: dict[tuple[str, str], MigrationFn] = {
    ("1.0", "1.0"): _noop_1_0,
}

#: The single legacy schema version the plain ``migrate`` helper targets.
CURRENT_SCHEMA_VERSION = "1.0"


def has_migration_path(from_version: str, to_version: str = CURRENT_SCHEMA_VERSION) -> bool:
    return (from_version, to_version) in MIGRATIONS


def migrate(
    document: dict[str, object],
    from_version: str,
    to_version: str = CURRENT_SCHEMA_VERSION,
) -> dict[str, object]:
    fn = MIGRATIONS.get((from_version, to_version))
    if fn is None:
        raise KeyError(f"no migration registered for {from_version} -> {to_version}")
    return fn(document)


def migrate_workout_1_0_to_1_1(
    workout_v1_0: WorkoutTemplateV1_0,
    *,
    explicit_default_start_mode: StartMode,
    workout_goal: WorkoutGoal = WorkoutGoal.CUSTOM,
) -> WorkoutTemplateV1_1:
    """Upgrade a 1.0 workout to 1.1. The start mode must be supplied explicitly.

    Distances, strokes, and pace segments are preserved exactly. No start mode is guessed:
    the caller decides whether the legacy workout was a dive or an in-water start.
    """
    if not isinstance(explicit_default_start_mode, StartMode):
        raise TypeError("explicit_default_start_mode must be a StartMode")
    return WorkoutTemplateV1_1(
        schemaVersion="1.1",
        name=workout_v1_0.name,
        poolLengthM=workout_v1_0.poolLengthM,
        stroke=workout_v1_0.stroke,
        startPolicy=StartPolicy(defaultMode=explicit_default_start_mode),
        workoutGoal=workout_goal,
        blocks=list(workout_v1_0.blocks),
    )
