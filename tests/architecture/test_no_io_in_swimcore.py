import pytest

from swimtools.arch_check import check_swimcore_purity

pytestmark = pytest.mark.architecture


def test_swimcore_has_no_io_or_nondeterminism() -> None:
    """swimcore'da yasak import (time/uuid/random/os/socket...) VE dogrudan I/O built-in cagrisi
    (open/input/eval/exec) yoktur. Zaman/kimlik enjekte edilir (ADR-033)."""
    violations = check_swimcore_purity()
    assert not violations, "\n".join(str(v) for v in violations)
