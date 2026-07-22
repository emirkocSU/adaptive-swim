"""The Phase 1 e2e CLIs are thin, deterministic and typed (ADR-041 §12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.cases import REQUIRED_CASE_IDS, build_all_cases
from swimtools.run_e2e import EXIT_INVALID_INPUT, EXIT_OK
from swimtools.run_e2e import main as run_main
from swimtools.verify_e2e_bundle import main as verify_main


def test_list_shows_every_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_main(["--list"]) == EXIT_OK
    out = capsys.readouterr().out
    for case in build_all_cases():
        assert case.caseId in out
    for case_id in REQUIRED_CASE_IDS:
        assert case_id in out


def test_unknown_case_is_invalid_input(tmp_path: Path) -> None:
    assert run_main(["--case", "nope", "--output", str(tmp_path / "out")]) == EXIT_INVALID_INPUT


def test_case_and_all_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        run_main(["--all", "--case", "normal-continuous-completion", "--output", str(tmp_path)])


def test_output_is_required() -> None:
    with pytest.raises(SystemExit):
        run_main(["--case", "normal-continuous-completion"])


def test_json_output_and_verification_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "bundle"
    assert (
        run_main(
            [
                "--case",
                "normal-continuous-completion",
                "--seed",
                "42",
                "--output",
                str(output),
                "--format",
                "json",
            ]
        )
        == EXIT_OK
    )
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    summary = payload[0]
    assert summary["caseId"] == "normal-continuous-completion"
    assert summary["seed"] == 42
    assert summary["allChecksPassed"] is True
    assert summary["failedCheckCount"] == 0
    assert len(summary["journalSha256"]) == 64
    assert verify_main(["--bundle", str(output)]) == 0


def test_text_output_is_human_readable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        run_main(["--case", "stop-during-planned-rest", "--output", str(tmp_path / "text-bundle")])
        == EXIT_OK
    )
    out = capsys.readouterr().out
    assert "[PASS] stop-during-planned-rest" in out
    assert "manifestId:" in out
    assert "1/1 case(s) passed every invariant" in out


def test_verify_reports_a_missing_bundle(tmp_path: Path) -> None:
    assert verify_main(["--bundle", str(tmp_path / "absent")]) == EXIT_INVALID_INPUT
