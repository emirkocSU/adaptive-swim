"""Shared fixtures for the Phase 1 vertical-slice tests.

Every case is executed at most once per session and cached, because one case drives the
whole real stack (aggregate, journal, replay, analytics). Bundles are written into a
session-scoped temporary directory so no test depends on a repository path.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from e2e.cases import CASE_BY_ID, build_all_cases
from e2e.runner import run_phase1_vertical_slice
from e2e.types import Phase1E2EResult


@pytest.fixture(scope="session")
def e2e_root() -> Iterator[Path]:
    directory = Path(tempfile.mkdtemp(prefix="phase1-e2e-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(scope="session")
def run_case(e2e_root: Path) -> Callable[..., Phase1E2EResult]:
    cache: dict[tuple[str, int | None], Phase1E2EResult] = {}

    def _run(case_id: str, *, seed: int | None = None, label: str | None = None):
        key = (case_id, seed)
        if key in cache and label is None:
            return cache[key]
        builder = CASE_BY_ID[case_id]
        directory = e2e_root / (label or f"{case_id}-{seed if seed is not None else 'default'}")
        result = run_phase1_vertical_slice(case=builder(), output_directory=directory, seed=seed)
        if label is None:
            cache[key] = result
        return result

    return _run


@pytest.fixture(scope="session")
def all_results(run_case: Callable[..., Phase1E2EResult]) -> dict[str, Phase1E2EResult]:
    return {case.caseId: run_case(case.caseId) for case in build_all_cases()}
