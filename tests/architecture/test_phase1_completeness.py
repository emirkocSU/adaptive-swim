"""Mechanical Phase 1 closure must contain no temporary-success path."""

from __future__ import annotations

from swimtools.completeness_check import check_phase1_completeness


def test_repository_is_mechanically_complete() -> None:
    issues = check_phase1_completeness()
    assert issues == (), "\n".join(issue.render() for issue in issues)
