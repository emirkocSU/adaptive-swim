"""Mechanical Phase 1 closure check.

This command does not execute the test suite.  It proves that every required suite and
closure binding exists, that the Makefile has no temporary-success path, and that pytest
markers are unique.  The actual tests remain the responsibility of ``make ci``.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_REQUIRED_SUITES = (
    "unit",
    "property",
    "replay",
    "simulator",
    "analytics",
    "architecture",
    "e2e",
)
_REQUIRED_TOOLS = (
    "src/swimtools/gen_schemas.py",
    "src/swimtools/completeness_check.py",
)
_BINDING_PATTERN = re.compile(
    r"^- (I-P1-(?P<number>\d{2})) -> (?P<path>tests/[^:]+\.py)::(?P<test>test_[A-Za-z0-9_]+)$"
)
_EXPECTED_BINDING_IDS = tuple(f"I-P1-{index:02d}" for index in range(1, 21))


@dataclass(frozen=True, slots=True)
class CompletenessIssue:
    rule: str
    message: str

    def render(self) -> str:
        return f"[{self.rule}] {self.message}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _check_suites(root: Path) -> list[CompletenessIssue]:
    issues: list[CompletenessIssue] = []
    for suite in _REQUIRED_SUITES:
        directory = root / "tests" / suite
        tests = sorted(directory.glob("test_*.py")) if directory.is_dir() else []
        if not tests:
            issues.append(
                CompletenessIssue(
                    "suite.present",
                    f"tests/{suite} must exist and contain at least one test_*.py file",
                )
            )
    return issues


def _check_tools(root: Path) -> list[CompletenessIssue]:
    return [
        CompletenessIssue("tool.present", f"missing required tool: {relative}")
        for relative in _REQUIRED_TOOLS
        if not (root / relative).is_file()
    ]


def _check_makefile(root: Path) -> list[CompletenessIssue]:
    issues: list[CompletenessIssue] = []
    text = (root / "Makefile").read_text(encoding="utf-8")
    if re.search(r"\bPENDING\b", text, flags=re.IGNORECASE):
        issues.append(
            CompletenessIssue(
                "make.no_temporary_success",
                "Makefile must not contain a PENDING fallback or message",
            )
        )
    if not re.search(r"(?m)^phase1-completeness:\s*$", text):
        issues.append(
            CompletenessIssue(
                "make.completeness_target",
                "Makefile must define phase1-completeness",
            )
        )
    ci_match = re.search(r"(?m)^ci:\s*(?P<deps>.*(?:\\\n[\t ]+.*)*)", text)
    if ci_match is None or "phase1-completeness" not in ci_match.group("deps"):
        issues.append(
            CompletenessIssue(
                "make.ci_dependency",
                "ci must depend on phase1-completeness",
            )
        )
    if re.search(r"(?ms)^test-property:\s*\n\s*@?if\b", text):
        issues.append(
            CompletenessIssue(
                "make.property_real",
                "test-property must execute pytest directly, not conditionally succeed",
            )
        )
    return issues


def _check_markers(root: Path) -> list[CompletenessIssue]:
    issues: list[CompletenessIssue] = []
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    markers = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    names = [str(item).split(":", 1)[0].strip() for item in markers]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        issues.append(
            CompletenessIssue(
                "pytest.markers_unique",
                f"duplicate pytest marker definitions: {', '.join(duplicates)}",
            )
        )
    return issues


def _check_bindings(root: Path) -> list[CompletenessIssue]:
    issues: list[CompletenessIssue] = []
    path = root / "docs" / "testing" / "invariants.md"
    bindings: dict[str, tuple[str, str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = _BINDING_PATTERN.fullmatch(raw_line.strip())
        if match is None:
            continue
        invariant_id = match.group(1)
        if invariant_id in bindings:
            issues.append(
                CompletenessIssue(
                    "binding.unique",
                    f"duplicate closure binding: {invariant_id}",
                )
            )
        bindings[invariant_id] = (match.group("path"), match.group("test"))

    actual_ids = tuple(sorted(bindings))
    if actual_ids != _EXPECTED_BINDING_IDS:
        issues.append(
            CompletenessIssue(
                "binding.complete",
                "closure bindings must be exactly I-P1-01 through I-P1-20",
            )
        )

    for invariant_id, (relative, test_name) in sorted(bindings.items()):
        test_path = root / relative
        if not test_path.is_file():
            issues.append(
                CompletenessIssue(
                    "binding.file",
                    f"{invariant_id} points to missing file {relative}",
                )
            )
            continue
        try:
            functions = _test_functions(test_path)
        except (OSError, SyntaxError) as exc:
            issues.append(
                CompletenessIssue(
                    "binding.parse",
                    f"cannot parse {relative}: {exc}",
                )
            )
            continue
        if test_name not in functions:
            issues.append(
                CompletenessIssue(
                    "binding.function",
                    f"{invariant_id} points to missing test {relative}::{test_name}",
                )
            )
    return issues


def check_phase1_completeness(root: Path | None = None) -> tuple[CompletenessIssue, ...]:
    repo = _repo_root() if root is None else Path(root).resolve()
    issues = [
        *_check_suites(repo),
        *_check_tools(repo),
        *_check_makefile(repo),
        *_check_markers(repo),
        *_check_bindings(repo),
    ]
    return tuple(issues)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: python -m swimtools.completeness_check [repository-root]", file=sys.stderr)
        return 2
    root = Path(args[0]) if args else None
    issues = check_phase1_completeness(root)
    if issues:
        print("PHASE1 COMPLETENESS FAILED", file=sys.stderr)
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    print("phase1-completeness: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
