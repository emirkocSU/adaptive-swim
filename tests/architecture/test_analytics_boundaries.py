"""AST guardrails for the pure analytics package (ADR-040)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "src" / "analytics"
FORBIDDEN_IMPORTS = {
    "persistence",
    "simulator",
    "swimtools",
    "os",
    "pathlib",
    "random",
    "time",
    "socket",
    "requests",
    "httpx",
    "numpy",
    "pandas",
    "sklearn",
    "torch",
    "tensorflow",
}


def test_analytics_has_no_io_random_network_or_ml_dependencies() -> None:
    problems: list[str] = []
    for path in sorted(ANALYTICS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]}
            else:
                roots = set()
            for root in roots & FORBIDDEN_IMPORTS:
                problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {root}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"open", "input"}
            ):
                problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.func.id}()")
    assert problems == [], "analytics boundary violations:\n" + "\n".join(problems)


def test_swimcore_and_contracts_do_not_import_analytics() -> None:
    problems: list[str] = []
    for package in (ROOT / "src" / "swimcore", ROOT / "src" / "contracts"):
        for path in sorted(package.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    names = []
                if any(name == "analytics" or name.startswith("analytics.") for name in names):
                    problems.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert problems == []
