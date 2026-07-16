"""Pure-package guard: swimcore/contracts must not use I/O builtins or forbidden imports."""

from __future__ import annotations

from swimtools.arch_check import check_purity


def test_pure_packages_have_no_io_or_forbidden_imports() -> None:
    problems = check_purity()
    assert problems == [], "purity violations:\n" + "\n".join(problems)
