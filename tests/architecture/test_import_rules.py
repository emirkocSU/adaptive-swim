import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_import_linter_contracts_hold() -> None:
    """Katman sirasi ve yasak import'lar (external-data siniri dahil) gecerli."""
    result = subprocess.run(
        [sys.executable, "-m", "importlinter.cli", "lint-imports", "--config", ".importlinter"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
