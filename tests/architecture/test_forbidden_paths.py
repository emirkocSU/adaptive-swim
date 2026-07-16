"""No Phase-1-forbidden packages or empty future scaffolding may exist."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

FORBIDDEN = ("cloud", "ml", "ui", "ui_minimal", "edge", "adapters", "wearable_import")


def test_no_forbidden_directories() -> None:
    present = [name for name in FORBIDDEN if (SRC / name).exists()]
    assert present == [], f"forbidden Phase-1 directories present: {present}"


def test_no_partner_adapters() -> None:
    hits = list(SRC.rglob("partner_*"))
    assert hits == [], f"forbidden partner adapters present: {hits}"


def test_no_sqlite_in_contracts_or_swimcore() -> None:
    for pkg in ("contracts", "swimcore"):
        for py in (SRC / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            assert "import sqlite3" not in text, f"{py} imports sqlite3 (forbidden here)"
