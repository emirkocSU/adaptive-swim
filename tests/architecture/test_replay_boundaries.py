"""Commit 7 architecture boundaries (§22).

- ``swimcore.replay`` is pure: no persistence, no filesystem/socket, no real time,
  randomness or uuid, and no runtime clocks (`ActiveClock`/`GhostClock`) or
  ``SessionAggregate``.
- ``persistence`` uses no SQLite/DB, no FastAPI/web framework, no network.
- ``swimcore`` never imports ``persistence``.
The layered import-linter contract (swimtools > simulator > persistence > swimcore >
contracts) is verified by tests/architecture/test_import_rules.py and stays unchanged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

SRC = Path(__file__).resolve().parents[2] / "src"

#: Module roots/prefixes swimcore.replay must never import.
REPLAY_FORBIDDEN_PREFIXES = (
    "persistence",
    "simulator",
    "swimtools",
    "os",
    "pathlib",
    "io",
    "shutil",
    "tempfile",
    "socket",
    "ssl",
    "time",
    "datetime",
    "random",
    "uuid",
    "secrets",
    "sqlite3",
    "swimcore.time",
    "swimcore.ghost",
    "swimcore.session.aggregate",
    "swimcore.session.handler",
)

#: Module roots persistence must never import (DB / web / network).
PERSISTENCE_FORBIDDEN_PREFIXES = (
    "sqlite3",
    "sqlalchemy",
    "psycopg2",
    "psycopg",
    "pymongo",
    "redis",
    "fastapi",
    "flask",
    "django",
    "starlette",
    "uvicorn",
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "asyncio",
)


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _violations(package_dir: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    problems: list[str] = []
    for py in sorted(package_dir.rglob("*.py")):
        for module in _imports_of(py):
            for prefix in forbidden_prefixes:
                if module == prefix or module.startswith(prefix + "."):
                    problems.append(f"{py.relative_to(SRC.parent)}: imports {module}")
    return problems


def test_replay_is_pure_and_isolated() -> None:
    problems = _violations(SRC / "swimcore" / "replay", REPLAY_FORBIDDEN_PREFIXES)
    assert problems == [], "swimcore.replay boundary violations:\n" + "\n".join(problems)


def test_replay_does_not_reference_runtime_clocks_or_aggregate() -> None:
    banned_names = ("ActiveClock", "GhostClock", "SessionAggregate", "SimClock")
    problems: list[str] = []
    for py in sorted((SRC / "swimcore" / "replay").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned_names:
                problems.append(f"{py.name}:{node.lineno}: references {node.id}")
    assert problems == [], "\n".join(problems)


def test_persistence_has_no_db_web_or_network() -> None:
    problems = _violations(SRC / "persistence", PERSISTENCE_FORBIDDEN_PREFIXES)
    assert problems == [], "persistence boundary violations:\n" + "\n".join(problems)


def test_persistence_may_import_contracts_and_replay_only_downward() -> None:
    allowed_internal = ("contracts", "swimcore.replay", "swimcore.session", "persistence")
    problems: list[str] = []
    for py in sorted((SRC / "persistence").rglob("*.py")):
        for module in _imports_of(py):
            if module.startswith(
                ("contracts", "swimcore", "persistence")
            ) and not module.startswith(allowed_internal):
                problems.append(f"{py.name}: imports {module}")
    assert problems == [], "\n".join(problems)


def test_swimcore_never_imports_persistence() -> None:
    problems = _violations(SRC / "swimcore", ("persistence",))
    assert problems == [], "swimcore must not import persistence:\n" + "\n".join(problems)


def test_forbidden_phase1_packages_still_absent() -> None:
    for name in ("cloud", "ml", "ui", "ui_minimal", "edge", "adapters", "wearable_import"):
        assert not (SRC / name).exists(), f"forbidden Phase-1 package present: src/{name}"
