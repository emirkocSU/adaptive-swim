"""Golden schema tests + Commit 2 contract guardrails."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "src" / "contracts"
SCHEMA_DIR = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"

WORKOUT_SCHEMA = json.loads((SCHEMA_DIR / "workout-1.0.json").read_text(encoding="utf-8"))

BANNED_PACE_NAMES = ("minPace", "maxPace", "coachMinPace", "coachMaxPace")
CUSTOM_KEYWORDS = ("multipleOfPoolLength", "contiguousCoverage")

# Examples the JSON Schema itself rejects (structural).
SCHEMA_INVALID = {
    "custom_schema_keyword_not_allowed.json",
    "missing_required_workout_field.json",
    "invalid_pace_mode.json",
}


def _validator() -> jsonschema.protocols.Validator:
    cls = jsonschema.validators.validator_for(WORKOUT_SCHEMA)
    cls.check_schema(WORKOUT_SCHEMA)
    return cls(WORKOUT_SCHEMA)


def _valid_files() -> list[Path]:
    return sorted((EXAMPLES / "valid").glob("*.json"))


def _invalid_files() -> list[Path]:
    return sorted((EXAMPLES / "invalid").glob("*.json"))


def _semantic_invalid_files() -> list[Path]:
    return sorted((EXAMPLES / "semantic_invalid").glob("*.json"))


# ---------------------------------------------------------------- valid / invalid goldens
@pytest.mark.parametrize("path", _valid_files(), ids=lambda p: p.name)
def test_valid_examples_pass_schema(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    _validator().validate(doc)  # raises on failure


@pytest.mark.parametrize("path", _invalid_files(), ids=lambda p: p.name)
def test_invalid_examples_are_rejected_by_schema(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = list(_validator().iter_errors(doc))
    assert errors, f"{path.name} should be rejected by the JSON Schema"


@pytest.mark.parametrize("path", _semantic_invalid_files(), ids=lambda p: p.name)
def test_semantic_invalid_examples_pass_structural_schema(path: Path) -> None:
    # Structurally valid; the semantic defect is caught by the Commit 3 validator, not schema.
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = list(_validator().iter_errors(doc))
    assert not errors, (
        f"{path.name} is a semantic-level case and must pass structural schema; "
        "its defect is caught by the semantic validator in Commit 3"
    )


def test_every_invalid_example_is_classified() -> None:
    names = {p.name for p in _invalid_files()}
    assert names == SCHEMA_INVALID
    # semantic examples live in a separate directory and must not be mixed in.
    assert not (SCHEMA_INVALID & {p.name for p in _semantic_invalid_files()})


# ---------------------------------------------------------------- schema purity / vocabulary
def test_schema_has_no_custom_keywords() -> None:
    text = (SCHEMA_DIR / "workout-1.0.json").read_text(encoding="utf-8")
    for kw in CUSTOM_KEYWORDS:
        assert kw not in text, f"custom keyword {kw!r} leaked into the JSON Schema"


def test_schema_uses_additional_properties_false() -> None:
    assert WORKOUT_SCHEMA.get("additionalProperties") is False


def test_no_banned_pace_names_anywhere() -> None:
    for py in CONTRACTS.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for banned in BANNED_PACE_NAMES:
            assert banned not in text, f"banned pace name {banned!r} in {py}"
    for schema in SCHEMA_DIR.glob("*.json"):
        text = schema.read_text(encoding="utf-8")
        for banned in BANNED_PACE_NAMES:
            assert banned not in text, f"banned pace name {banned!r} in {schema}"


def test_locked_pace_vocabulary_present() -> None:
    text = (CONTRACTS / "workout.py").read_text(encoding="utf-8")
    for name in (
        "targetPaceSecPer100M",
        "fastestAllowedPaceSecPer100M",
        "slowestAllowedPaceSecPer100M",
    ):
        assert name in text


# ---------------------------------------------------------------- StopPause terminology
def test_no_general_incident_event_names() -> None:
    events = (CONTRACTS / "events.py").read_text(encoding="utf-8")
    enums = (CONTRACTS / "enums.py").read_text(encoding="utf-8")
    for banned in ("IncidentStarted", "IncidentResolved"):
        assert banned not in events, f"{banned} must not be a general event name"
        assert banned not in enums, f"{banned} must not be a general event name"


def test_stoppause_terminology_used() -> None:
    enums = (CONTRACTS / "enums.py").read_text(encoding="utf-8")
    for token in ("StopDetected", "LongStopConfirmed", "StopPauseStarted", "StopPauseResolved"):
        assert token in enums
    # MANUAL_INCIDENT survives only as a trigger.
    assert "MANUAL_INCIDENT" in enums
    assert Path(CONTRACTS / "stop_pause.py").exists()
    assert not Path(CONTRACTS / "incident.py").exists()


# ---------------------------------------------------------------- duration accounting
def test_duration_accounting_fields_present() -> None:
    analytics = (CONTRACTS / "analytics.py").read_text(encoding="utf-8")
    for field in ("activeDurationSec", "stoppedDurationSec", "elapsedDurationSec"):
        assert field in analytics


def test_performance_related_stop_probability_is_optional_advisory() -> None:
    from contracts.analytics import TrainingEfficiencyMetrics

    field = TrainingEfficiencyMetrics.model_fields["performanceRelatedStopProbability"]
    assert not field.is_required(), "advisory field must be optional"
    assert field.default is None


# ---------------------------------------------------------------- schema-check parity
def test_generated_schema_matches_committed() -> None:
    result = subprocess.run(
        ["python", "-m", "swimtools.gen_schemas", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), **_os_environ()},
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)
