"""Leakage guard tests (Commit 8, corrected §15, ADR-039 §11)."""

from __future__ import annotations

import pytest

from swimtools.data_splitting import (
    LeakageError,
    validate_athlete_group_partition,
    validate_crossover_group_partition,
    validate_feature_allowlist,
    validate_partition_plan,
    validate_pre_post_group_partition,
    validate_race_group_partition,
    validate_time_aware_partition,
    validate_time_series_group_partition,
    validate_trial_group_partition,
)


def test_same_race_in_two_partitions_is_rejected() -> None:
    with pytest.raises(LeakageError, match="race_uid"):
        validate_race_group_partition(["r1", "r1", "r2"], ["train", "test", "train"])


def test_race_grouped_split_passes() -> None:
    validate_race_group_partition(["r1", "r1", "r2"], ["train", "train", "test"])


def test_same_athlete_in_train_and_test_is_rejected() -> None:
    with pytest.raises(LeakageError, match="athlete"):
        validate_athlete_group_partition(["a1", "a1"], ["train", "test"])


def test_trial_repeats_cannot_be_split() -> None:
    with pytest.raises(LeakageError, match="trial"):
        validate_trial_group_partition(["t1", "t1", "t1"], ["train", "train", "test"])


def test_pre_post_cannot_be_split() -> None:
    with pytest.raises(LeakageError, match="pre/post"):
        validate_pre_post_group_partition(["s1", "s1"], ["pre", "post"], ["train", "test"])


def test_first_and_second_25_cannot_be_split() -> None:
    """First/second-25 rows of one athlete and study period share a partition."""
    with pytest.raises(LeakageError):
        validate_partition_plan(
            grouping={"subject_period": ["s1-p1", "s1-p1"]},
            partitions=["train", "test"],
            grouping_keys=["subject_period"],
        )


def test_massage_crossover_cannot_be_split() -> None:
    with pytest.raises(LeakageError, match="crossover"):
        validate_crossover_group_partition(["s1", "s1"], ["massage", "control"], ["train", "test"])


def test_crossover_requires_condition_labels() -> None:
    with pytest.raises(LeakageError, match="condition_label"):
        validate_crossover_group_partition(["s1", "s1"], ["massage", ""], ["train", "train"])


def test_imu_time_series_cannot_be_split() -> None:
    with pytest.raises(LeakageError, match="time-series"):
        validate_time_series_group_partition(["sess1", "sess1"], ["train", "test"])


def test_time_aware_partition_rejects_lookahead() -> None:
    with pytest.raises(LeakageError, match="time-aware"):
        validate_time_aware_partition([10.0, 30.0, 20.0], ["train", "train", "test"])


def test_time_aware_partition_accepts_ordered_split() -> None:
    validate_time_aware_partition([10.0, 20.0, 30.0], ["train", "train", "test"])


def test_future_target_column_cannot_be_a_feature() -> None:
    with pytest.raises(LeakageError, match="forecast label"):
        validate_feature_allowlist(
            ["load", "next_week_performance"], ["next_week_performance", "next_week_load"]
        )


def test_feature_allowlist_passes_without_labels() -> None:
    validate_feature_allowlist(["load", "rpe"], ["next_week_performance"])


def test_partition_plan_reports_a_missing_grouping_key() -> None:
    with pytest.raises(LeakageError, match="missing"):
        validate_partition_plan(
            grouping={"race_uid": ["r1"]}, partitions=["train"], grouping_keys=["athlete_uid"]
        )


def test_mismatched_lengths_are_rejected() -> None:
    with pytest.raises(LeakageError, match="equal length"):
        validate_race_group_partition(["r1", "r2"], ["train"])
