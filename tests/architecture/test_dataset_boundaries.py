"""Dataset-layer architecture boundaries (Commit 8 corrected §16)."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_REPO = _SRC.parent


def _all_py(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
            modules.add(node.module)
    return modules


def test_swimcore_reads_no_dataset_or_tabular_format() -> None:
    banned = {"csv", "zipfile", "pandas", "numpy", "scipy", "pyarrow"}
    for path in _all_py(_SRC / "swimcore"):
        assert not (_imported_modules(path) & banned), f"{path.name} imports a dataset module"


def test_swimcore_does_not_import_dataset_or_forecast_contracts() -> None:
    for path in _all_py(_SRC / "swimcore"):
        modules = _imported_modules(path)
        assert "contracts.data_assets" not in modules, f"{path.name} imports contracts.data_assets"
        assert "contracts.forecasting" not in modules, f"{path.name} imports contracts.forecasting"


def test_contracts_perform_no_io() -> None:
    banned = {"csv", "zipfile", "pathlib", "open", "requests", "httpx", "sqlite3"}
    for path in _all_py(_SRC / "contracts"):
        modules = _imported_modules(path)
        assert not (modules & banned), f"{path.name} performs I/O"


def test_dataset_validator_lives_in_swimtools_only() -> None:
    assert (_SRC / "swimtools" / "validate_dataset_bundle.py").is_file()
    assert (_SRC / "swimtools" / "data_catalog.py").is_file()
    for package in ("swimcore", "contracts", "persistence", "simulator"):
        for path in _all_py(_SRC / package):
            modules = _imported_modules(path)
            assert "swimtools.validate_dataset_bundle" not in modules, (
                f"{path.name} imports the dataset validator"
            )
            assert "swimtools.data_catalog" not in modules, (
                f"{path.name} imports the dataset catalog"
            )


def test_simulator_reads_no_dataset() -> None:
    banned = {"csv", "zipfile", "pandas", "numpy"}
    for path in _all_py(_SRC / "simulator"):
        modules = _imported_modules(path)
        assert not (modules & banned), f"{path.name} imports a dataset module"
        assert "swimtools" not in modules, f"{path.name} imports swimtools (layer inversion)"


def test_src_ml_is_not_created_in_phase_one() -> None:
    assert not (_SRC / "ml").exists(), "src/ml must not exist before Phase 5"


def test_runtime_has_no_pandas_or_numpy_dependency() -> None:
    text = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    runtime = text.split("[project.optional-dependencies]")[0]
    for banned in ("pandas", "numpy", "scipy"):
        assert banned not in runtime, f"{banned} became a runtime dependency"


def test_raw_datasets_are_not_packaged() -> None:
    data_dir = _REPO / "data"
    assert (data_dir / "catalog").is_dir()
    assert (data_dir / "schemas").is_dir()
    for path in data_dir.rglob("*"):
        if path.is_file():
            assert path.suffix.lower() not in {".csv", ".zip"}, f"raw data committed: {path}"
    for path in _SRC.rglob("*"):
        if path.is_file():
            assert path.suffix.lower() not in {".csv", ".zip"}, f"data inside src/: {path}"


def test_catalog_manifests_stay_small() -> None:
    for path in (_REPO / "data" / "catalog").glob("*.json"):
        assert path.stat().st_size < 32_000, f"{path.name} is too large to be metadata"
