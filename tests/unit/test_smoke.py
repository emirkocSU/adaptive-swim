"""Smoke: contracts import and the five source packages exist."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_source_packages_present() -> None:
    for pkg in ("contracts", "swimcore", "persistence", "simulator", "swimtools"):
        assert (SRC / pkg / "__init__.py").exists(), f"missing package {pkg}"


def test_contracts_import() -> None:
    import contracts.analytics  # noqa: F401
    import contracts.commands  # noqa: F401
    import contracts.enums  # noqa: F401
    import contracts.events  # noqa: F401
    import contracts.external_data  # noqa: F401
    import contracts.ghost  # noqa: F401
    import contracts.pacing  # noqa: F401
    import contracts.splits  # noqa: F401
    import contracts.stop_pause  # noqa: F401
    import contracts.workout  # noqa: F401
