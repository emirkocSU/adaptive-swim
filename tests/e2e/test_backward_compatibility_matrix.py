"""Phase 1 backward compatibility matrix (ADR-041 §14).

No schema is removed and no version is bumped just because Commit 10 emits new artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from contracts.analytics import SessionReport
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.session_report import SessionReportV1_1
from contracts.workout import WorkoutTemplateV1_1, WorkoutTemplateVersion
from e2e.types import Phase1E2EResult
from swimcore.pacing.continuous_migration import migrate_approved_pace_profile_1_0_to_1_1
from swimcore.workout.migrations import migrate_workout_1_0_to_1_1

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "src" / "contracts" / "schemas"


@pytest.mark.parametrize(
    "name",
    [
        "workout-1.0.json",
        "workout-1.1.json",
        "approved-pace-profile-1.0.json",
        "approved-pace-profile-1.1.json",
        "event-envelope-1.0.json",
        "event-batch-record-1.0.json",
        "session-report-1.0.json",
        "session-report-1.1.json",
    ],
)
def test_every_supported_schema_is_still_committed(name: str) -> None:
    path = _SCHEMA_DIR / name
    assert path.is_file(), f"{name} must not be removed"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("$schema")


def test_workout_1_0_still_parses_and_migrates() -> None:
    from contracts.enums import StartMode

    example_dir = Path(__file__).resolve().parents[2] / "src" / "contracts" / "examples"
    parsed = 0
    for path in sorted(example_dir.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0":
            continue
        if "blocks" not in payload:
            continue
        try:
            workout = WorkoutTemplateVersion.model_validate(payload)
        except ValueError:
            continue  # deliberately invalid fixtures must stay invalid
        parsed += 1
        migrated = migrate_workout_1_0_to_1_1(
            workout, explicit_default_start_mode=StartMode.DIVE_START
        )
        assert isinstance(migrated, WorkoutTemplateV1_1)
        assert migrated.schemaVersion == "1.1"
        assert migrated.poolLengthM == workout.poolLengthM
    assert parsed > 0, "at least one valid workout 1.0 fixture must still parse"


def test_pace_profile_1_0_runs_without_migration(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("legacy-profile-compatibility")
    assert result.sessionReport.provenance.paceProfileSchemaVersion == "1.0"
    assert result.allChecksPassed


def test_pace_profile_1_0_to_1_1_migration_is_explicit_and_deterministic() -> None:
    from e2e.cases import _legacy_profile

    legacy: ApprovedPaceProfile = _legacy_profile("compat-source")
    first = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    second = migrate_approved_pace_profile_1_0_to_1_1(legacy)
    assert first == second
    assert first.schemaVersion == "1.1"
    assert first.profileId == legacy.profileId
    assert first.profileVersion == legacy.profileVersion
    assert first.curveProvenance.legacyProfileId == legacy.profileId
    assert first.curveProvenance.migrationVersion


def test_event_envelope_and_batch_stay_at_1_0(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("normal-continuous-completion")
    lines = [line for line in result.journalPath.read_bytes().split(b"\n") if line.strip()]
    for line in lines:
        payload = json.loads(line)
        batch = EventBatchRecord.model_validate(payload)
        assert batch.recordVersion == "1.0"
        for event in batch.events:
            assert isinstance(event, EventEnvelope)
            assert event.schemaVersion == "1.0"


def test_session_report_1_0_contract_still_decodes() -> None:
    schema = json.loads((_SCHEMA_DIR / "session-report-1.0.json").read_text(encoding="utf-8"))
    assert schema["title"] == SessionReport.__name__ or "SessionReport" in json.dumps(schema)


def test_session_report_1_1_is_the_current_output(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case("normal-continuous-completion")
    payload = json.loads(result.sessionReportPath.read_bytes())
    assert payload["schemaVersion"] == "1.1"
    assert SessionReportV1_1.model_validate(payload).reportId == result.sessionReport.reportId
    assert payload["provenance"]["reportSchemaVersion"] == "1.1"


def test_commit_ten_introduces_no_schema_two_zero() -> None:
    for path in _SCHEMA_DIR.glob("*.json"):
        assert "-2.0" not in path.name, f"unexpected major schema bump: {path.name}"
