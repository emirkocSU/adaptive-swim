"""Architecture boundaries of the Phase 1 e2e layer (ADR-041 §17)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
E2E = SRC / "e2e"

#: Packages that must never import the e2e layer (the arrow points outward only).
INNER_PACKAGES = ("swimcore", "contracts", "analytics", "persistence")

#: Modules the e2e layer must never import.
FORBIDDEN_E2E_IMPORTS = {
    "random",
    "secrets",
    "uuid",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "http",
    "asyncio",
    "sqlite3",
    "pandas",
    "numpy",
    "scipy",
    "torch",
}


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_inner_packages_never_import_e2e() -> None:
    problems: list[str] = []
    for package in INNER_PACKAGES:
        for path in _py_files(SRC / package):
            if "e2e" in _imported_roots(path):
                problems.append(str(path.relative_to(ROOT)))
    assert problems == [], f"inner packages importing e2e: {problems}"


def test_e2e_imports_no_forbidden_module() -> None:
    problems: list[str] = []
    for path in _py_files(E2E):
        for root in _imported_roots(path) & FORBIDDEN_E2E_IMPORTS:
            problems.append(f"{path.relative_to(ROOT)}: {root}")
    assert problems == [], f"forbidden e2e imports: {problems}"


def test_e2e_never_sleeps_or_reads_the_wall_clock() -> None:
    problems: list[str] = []
    for path in _py_files(E2E):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("time.sleep", "time.time(", "datetime.now", "utcnow", "perf_counter"):
            if forbidden in text:
                problems.append(f"{path.relative_to(ROOT)}: {forbidden}")
    assert problems == [], f"non-deterministic e2e code: {problems}"


def test_e2e_does_not_reimplement_domain_logic() -> None:
    """No second PCHIP, replay reducer or report metric implementation lives in e2e."""
    banned_tokens = (
        "def build_pchip",
        "class PchipInterpolator",
        "def replay_session",
        "def build_session_report",
        "def compile_continuous_pace_profile",
        "def compile_pace_timeline",
        "fritsch",
    )
    problems: list[str] = []
    for path in _py_files(E2E):
        text = path.read_text(encoding="utf-8").lower()
        for token in banned_tokens:
            if token.lower() in text:
                problems.append(f"{path.relative_to(ROOT)}: {token}")
    assert problems == [], f"e2e re-implements domain logic: {problems}"


def test_e2e_uses_the_real_public_apis() -> None:
    runner = (E2E / "runner.py").read_text(encoding="utf-8")
    for expected in (
        "from simulator.harness import",
        "from swimcore.replay.reducer import replay_session",
        "from persistence.jsonl_event_log import JsonlSessionEventLog",
        "build_session_report",
    ):
        assert expected in runner, f"runner must use the real component: {expected}"


def test_e2e_layer_order_is_respected() -> None:
    """e2e may import inward only; swimtools may import e2e."""
    allowed = {
        "e2e",
        "simulator",
        "analytics",
        "persistence",
        "swimcore",
        "contracts",
        "hashlib",
        "json",
        "shutil",
        "pathlib",
        "dataclasses",
        "collections",
        "enum",
        "math",
        "typing",
        "__future__",
    }
    problems: list[str] = []
    for path in _py_files(E2E):
        for root in _imported_roots(path):
            if root not in allowed:
                problems.append(f"{path.relative_to(ROOT)}: {root}")
    assert problems == [], f"unexpected e2e dependencies: {problems}"


def test_e2e_writes_no_absolute_path_into_artifacts() -> None:
    """The manifest model carries no path-shaped field."""
    manifest = (E2E / "manifest.py").read_text(encoding="utf-8")
    for banned in (": Path", "Path(", "os.path"):
        assert banned not in manifest, f"manifest must stay path-free: {banned}"


def test_src_ml_still_does_not_exist() -> None:
    assert not (SRC / "ml").exists(), "Commit 10 must not start ML development"
