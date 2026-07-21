"""Architecture guardrails for the simulator and continuous-curve layers (Commit 8 §40)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_SRC = Path(__file__).resolve().parents[2] / "src"
_SIM = _SRC / "simulator"
_PACING = _SRC / "swimcore" / "pacing"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            names.add(node.name)
    return names


def _all_py(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


# --------------------------------------------------------------- simulator must not duplicate
_FORBIDDEN_SIMULATOR_DEFS = {
    "GhostClock",
    "ActiveClock",
    "SimClock",
    "SafetyController",
    "PchipInterpolator",
    "PaceTimeline",
    "replay_session",
    "SessionAggregate",
}


def test_simulator_does_not_redefine_core_types() -> None:
    for path in _all_py(_SIM):
        defined = _defined_names(path)
        clash = defined & _FORBIDDEN_SIMULATOR_DEFS
        assert not clash, f"{path.name} redefines core type(s): {clash}"


def test_simulator_defines_no_pchip_or_pace_compiler() -> None:
    for path in _all_py(_SIM):
        text = path.read_text(encoding="utf-8")
        assert "fritsch" not in text.lower(), f"{path.name} appears to reimplement PCHIP"
        assert "def build_pchip" not in text
        assert "100.0 / " not in text or "speed" not in text.lower() or path.name == "provenance.py"


def test_simulator_imports_real_core() -> None:
    joined = "\n".join(p.read_text(encoding="utf-8") for p in _all_py(_SIM))
    assert "swimcore.session" in joined
    assert "persistence" in joined


def test_simulator_uses_no_network_or_sleep() -> None:
    for path in _all_py(_SIM):
        modules = _imported_modules(path)
        text = path.read_text(encoding="utf-8")
        for banned in ("socket", "ssl", "http", "urllib", "requests", "httpx", "asyncio"):
            assert banned not in modules, f"{path.name} imports {banned}"
        assert "time.sleep" not in text, f"{path.name} uses time.sleep"


def test_swimcore_does_not_import_simulator() -> None:
    for path in _all_py(_SRC / "swimcore"):
        for module in _imported_modules(path):
            assert not module.startswith("simulator"), f"{path} imports simulator"


def test_swimcore_does_not_import_persistence_or_external_data() -> None:
    for path in _all_py(_SRC / "swimcore"):
        for module in _imported_modules(path):
            assert not module.startswith("persistence"), f"{path} imports persistence"
            assert module != "contracts.external_data", f"{path} imports external_data"


# --------------------------------------------------------------- continuous curve purity
def test_continuous_curve_math_has_no_io_or_random() -> None:
    for name in ("pchip.py", "continuous_curve.py", "continuous_profile_compiler.py"):
        path = _PACING / name
        modules = _imported_modules(path)
        for banned in ("random", "os", "socket", "time", "secrets", "pathlib"):
            assert banned not in modules, f"{name} imports {banned}"
        text = path.read_text(encoding="utf-8")
        assert "import numpy" not in text
        assert "import scipy" not in text


def test_pchip_defined_only_once() -> None:
    definitions = [p for p in _all_py(_SRC) if "def build_pchip" in p.read_text(encoding="utf-8")]
    assert len(definitions) == 1, f"PCHIP defined in multiple places: {definitions}"


def test_no_forbidden_phase_packages() -> None:
    for name in ("cloud", "ml", "ui", "device", "wearable"):
        assert not (_SRC / name).exists(), f"forbidden package src/{name} present"


def test_no_sqlite_import_anywhere_in_src() -> None:
    for path in _all_py(_SRC):
        assert "sqlite3" not in _imported_modules(path), f"{path} imports sqlite3"
