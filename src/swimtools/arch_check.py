"""Architecture guard CLI: forbidden directories + purity AST scan + import-linter.

Fails if:
- any Phase-1-forbidden package directory exists under ``src/``;
- ``swimcore`` (or ``contracts``) uses forbidden builtins (``open``/``input``/``eval``/
  ``exec``/``__import__``) or imports I/O, network, database, or web-framework modules;
- import-linter contracts are broken.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]

# Directories that must not exist in Phase 1 (no empty future packages either).
_FORBIDDEN_DIRS = ("cloud", "ml", "ui", "ui_minimal", "edge", "adapters", "wearable_import")

# Packages whose purity is enforced by the AST scan.
_PURE_PACKAGES = ("swimcore", "contracts", "analytics")

# Builtins that imply I/O / dynamic execution — banned inside pure packages.
_FORBIDDEN_CALLS = frozenset({"open", "input", "eval", "exec", "__import__"})

# Top-level modules that imply filesystem / network / database / framework — banned.
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        # filesystem / process / io
        "io",
        "os",
        "pathlib",
        "shutil",
        "tempfile",
        "subprocess",
        "sys",
        # network
        "socket",
        "ssl",
        "asyncio",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        # database
        "sqlite3",
        "sqlalchemy",
        "psycopg2",
        "psycopg",
        "pymongo",
        "redis",
        # web / app frameworks
        "fastapi",
        "flask",
        "django",
        "starlette",
        "uvicorn",
        "pydantic_settings",
    }
)


def check_forbidden_dirs() -> list[str]:
    problems: list[str] = []
    for name in _FORBIDDEN_DIRS:
        if (_SRC / name).exists():
            problems.append(f"forbidden Phase-1 directory present: src/{name}")
    for path in _SRC.rglob("partner_*"):
        problems.append(f"forbidden partner adapter present: {path}")
    return problems


def _scan_file(path: Path) -> list[str]:
    problems: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(_SRC.parent)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALLS:
                problems.append(f"{rel}:{node.lineno}: forbidden call {node.func.id}()")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_CALLS:
            # bare reference (e.g. passing ``open`` around) is also forbidden
            if not isinstance(getattr(node, "ctx", None), ast.Store):
                problems.append(f"{rel}:{node.lineno}: forbidden reference {node.id}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORT_ROOTS:
                    problems.append(f"{rel}:{node.lineno}: forbidden import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                problems.append(f"{rel}:{node.lineno}: forbidden import from {node.module}")
    return problems


def _check_package_purity(pkg: str) -> list[str]:
    problems: list[str] = []
    pkg_dir = _SRC / pkg
    if not pkg_dir.exists():
        return problems
    for path in sorted(pkg_dir.rglob("*.py")):
        problems.extend(_scan_file(path))
    return problems


def check_purity() -> list[str]:
    problems: list[str] = []
    for pkg in _PURE_PACKAGES:
        problems.extend(_check_package_purity(pkg))
    return problems


def check_swimcore_purity() -> list[str]:
    """Purity violations scoped to the ``swimcore`` package only."""
    return _check_package_purity("swimcore")


def run_import_linter() -> int:
    return subprocess.call(["lint-imports"])  # noqa: S603,S607


def main() -> int:
    problems = check_forbidden_dirs() + check_purity()
    for p in problems:
        print(p)
    if problems:
        print(f"arch-check: FAILED ({len(problems)} problem(s))")
        return 1
    rc = run_import_linter()
    print("arch-check: OK" if rc == 0 else "arch-check: import-linter FAILED")
    return rc


if __name__ == "__main__":
    sys.exit(main())
