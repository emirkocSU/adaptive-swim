"""Pure leakage-guard validators for dataset partitioning (ADR-039, plan §11).

These helpers train nothing and read nothing. They take record identifiers plus partition
labels and check that a proposed split respects the grouping rules of the source dataset:

- one race, athlete, trial, session or crossover unit never spans two partitions;
- pre/post and first/second-25 records of one athlete stay together;
- an IMU time series is never cut across partitions;
- an athlete-week split stays time-aware (no future record in train after a test record);
- future target columns never enter the feature allowlist.

Every function raises :class:`LeakageError` with an explicit, machine-readable message on
violation and returns ``None`` on success. Pure, deterministic, stdlib-only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class LeakageError(Exception):
    """A proposed partitioning would leak information across train/test boundaries."""


def _group_partitions(
    group_ids: Sequence[object], partitions: Sequence[object], label: str
) -> dict[object, set[object]]:
    if len(group_ids) != len(partitions):
        raise LeakageError(
            f"{label}: group_ids and partitions must have equal length "
            f"({len(group_ids)} != {len(partitions)})"
        )
    mapping: dict[object, set[object]] = {}
    for group, partition in zip(group_ids, partitions, strict=True):
        mapping.setdefault(group, set()).add(partition)
    return mapping


def _assert_single_partition(
    group_ids: Sequence[object], partitions: Sequence[object], label: str
) -> None:
    mapping = _group_partitions(group_ids, partitions, label)
    offenders = sorted(
        (str(g), sorted(str(p) for p in ps)) for g, ps in mapping.items() if len(ps) > 1
    )
    if offenders:
        raise LeakageError(
            f"{label}: {len(offenders)} group(s) span multiple partitions, e.g. "
            f"{offenders[0][0]} -> {offenders[0][1]}"
        )


def validate_race_group_partition(
    race_uids: Sequence[object], partitions: Sequence[object]
) -> None:
    """One ``race_uid`` must live in exactly one partition (no segment-level leakage)."""
    _assert_single_partition(race_uids, partitions, "race_uid partition")


def validate_athlete_group_partition(
    athlete_ids: Sequence[object], partitions: Sequence[object]
) -> None:
    """One athlete must live in exactly one partition (athlete held-out evaluation)."""
    _assert_single_partition(athlete_ids, partitions, "athlete partition")


def validate_trial_group_partition(
    trial_ids: Sequence[object], partitions: Sequence[object]
) -> None:
    """All repeats of one trial/session must stay in one partition."""
    _assert_single_partition(trial_ids, partitions, "trial partition")


def validate_pre_post_group_partition(
    subject_ids: Sequence[object],
    phase_labels: Sequence[object],
    partitions: Sequence[object],
) -> None:
    """Pre and post records of one subject must stay in the same partition."""
    if not (len(subject_ids) == len(phase_labels) == len(partitions)):
        raise LeakageError("pre/post partition: all input sequences must have equal length")
    _assert_single_partition(subject_ids, partitions, "pre/post partition")


def validate_crossover_group_partition(
    crossover_unit_ids: Sequence[object],
    condition_labels: Sequence[object],
    partitions: Sequence[object],
) -> None:
    """A crossover unit (all conditions of one subject) must stay in one partition."""
    if not (len(crossover_unit_ids) == len(condition_labels) == len(partitions)):
        raise LeakageError("crossover partition: all input sequences must have equal length")
    if any(label is None or str(label) == "" for label in condition_labels):
        raise LeakageError(
            "crossover partition: every record needs a condition_label; an unconditioned "
            "view of an intervention study may not be built"
        )
    _assert_single_partition(crossover_unit_ids, partitions, "crossover partition")


def validate_time_series_group_partition(
    series_ids: Sequence[object], partitions: Sequence[object]
) -> None:
    """One continuous sensor time series must never be split across partitions."""
    _assert_single_partition(series_ids, partitions, "time-series partition")


def validate_time_aware_partition(
    timestamps: Sequence[float],
    partitions: Sequence[object],
    *,
    train_label: object = "train",
    test_label: object = "test",
) -> None:
    """Every training record must precede every test record (no lookahead)."""
    if len(timestamps) != len(partitions):
        raise LeakageError("time-aware partition: sequences must have equal length")
    train_times = [t for t, p in zip(timestamps, partitions, strict=True) if p == train_label]
    test_times = [t for t, p in zip(timestamps, partitions, strict=True) if p == test_label]
    if not train_times or not test_times:
        return
    latest_train = max(train_times)
    earliest_test = min(test_times)
    if latest_train >= earliest_test:
        raise LeakageError(
            f"time-aware partition: a training record at {latest_train} is not earlier than "
            f"the first test record at {earliest_test}"
        )


def validate_feature_allowlist(
    feature_columns: Sequence[str], forbidden_columns: Sequence[str]
) -> None:
    """A future target / label column may never appear in the feature allowlist."""
    forbidden = set(forbidden_columns)
    offenders = sorted(c for c in feature_columns if c in forbidden)
    if offenders:
        raise LeakageError(f"feature allowlist contains forecast label column(s): {offenders}")


def validate_partition_plan(
    *,
    grouping: Mapping[str, Sequence[object]],
    partitions: Sequence[object],
    grouping_keys: Sequence[str],
) -> None:
    """Convenience: assert every named grouping key stays inside a single partition."""
    for key in grouping_keys:
        values = grouping.get(key)
        if values is None:
            raise LeakageError(f"grouping key {key!r} missing from the partition plan")
        _assert_single_partition(values, partitions, f"{key} partition")


__all__ = [
    "LeakageError",
    "validate_athlete_group_partition",
    "validate_crossover_group_partition",
    "validate_feature_allowlist",
    "validate_partition_plan",
    "validate_pre_post_group_partition",
    "validate_race_group_partition",
    "validate_time_aware_partition",
    "validate_time_series_group_partition",
    "validate_trial_group_partition",
]
