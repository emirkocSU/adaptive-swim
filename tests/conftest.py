"""Shared test fixtures."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
CONTRACTS = SRC / "contracts"


@pytest.fixture(autouse=True)
def _deterministic_seed() -> None:
    random.seed(1234)


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def contracts_dir() -> Path:
    return CONTRACTS
