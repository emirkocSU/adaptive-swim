"""Architecture guard CLI: forbidden directories + import-linter.

Fails if any Phase-1-forbidden package directory exists under ``src/``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]

# Directories that must not exist in Phase 1 (no empty future packages either).
_FORBIDDEN_DIRS = ("cloud", "ml", "ui", "ui_minimal", "edge", "adapters", "wearable_import")


def check_forbidden_dirs() -> list[str]:
    problems: list[str] = []
    for name in _FORBIDDEN_DIRS:
        if (_SRC / name).exists():
            problems.append(f"forbidden Phase-1 directory present: src/{name}")
    # partner adapters anywhere
    for path in _SRC.rglob("partner_*"):
        problems.append(f"forbidden partner adapter present: {path}")
    return problems


def run_import_linter() -> int:
    return subprocess.call(["lint-imports"])  # noqa: S603,S607


def main() -> int:
    problems = check_forbidden_dirs()
    for p in problems:
        print(p)
    if problems:
        return 1
    return run_import_linter()


if __name__ == "__main__":
    sys.exit(main())
