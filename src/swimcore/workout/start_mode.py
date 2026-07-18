"""Deterministic start-mode resolution for Workout 1.1.

Precedence (highest first): per-repeat override → block-level start mode → workout default.
The resolved start mode is never ambiguous — a 1.1 workout always has a default, and every
override respects the workout's ``StartPolicy``.
"""

from __future__ import annotations

from contracts.enums import StartMode
from contracts.workout import WorkoutTemplateV1_1


class StartModeResolutionError(Exception):
    """A start-mode override is inconsistent with the workout's StartPolicy."""


def resolve_repeat_start_mode(
    workout: WorkoutTemplateV1_1,
    block_index: int,
    repeat_index: int,
) -> StartMode:
    """Resolve the start mode for a specific (block, repeat) execution.

    ``repeat_index`` is 0-based within the block's repetitions.
    """
    block = workout.blocks[block_index]
    if not (0 <= repeat_index < block.repetitions):
        raise StartModeResolutionError(
            f"repeat_index {repeat_index} out of range for block {block_index} "
            f"({block.repetitions} repetitions)"
        )

    # 1) per-repeat override (validated against the policy at construction time), matched
    #    on the (block, repeat) pair so two blocks' repeat 0 do not collide.
    for ov in workout.repeatOverrides:
        if (
            ov.blockIndex == block_index
            and ov.repeatIndex == repeat_index
            and ov.startMode is not None
        ):
            if not workout.startPolicy.allowRepeatOverride:
                raise StartModeResolutionError("repeat override present but policy disallows it")
            return ov.startMode

    # 2) block-level start mode
    if block.startMode is not None:
        if not workout.startPolicy.allowBlockOverride:
            raise StartModeResolutionError("block start mode present but policy disallows it")
        return block.startMode

    # 3) workout default
    return workout.startPolicy.defaultMode


def resolve_default_start_mode(workout: WorkoutTemplateV1_1) -> StartMode:
    """The workout-level default start mode (never ambiguous in 1.1)."""
    return workout.startPolicy.defaultMode
