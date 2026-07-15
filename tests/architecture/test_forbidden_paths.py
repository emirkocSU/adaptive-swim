import pytest

from swimtools.arch_check import check_forbidden_dirs

pytestmark = pytest.mark.architecture


def test_no_forbidden_directories() -> None:
    """cloud/, ml/, ui/, adapters/, edge/ Faz 1'de var olamaz (CLAUDE.md #3)."""
    violations = check_forbidden_dirs()
    assert not violations, "\n".join(str(v) for v in violations)
