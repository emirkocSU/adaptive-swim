"""Mimari uygunluk kontrolleri: yasak dizinler ve swimcore saflığı.

Faz 1'de cloud, ML runtime, UI ve cihaz sürücüsü yoktur. Bu kontroller onu
repository'nin mekanik bir özelliği yapar — bir disiplin meselesi değil.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

# Faz 1'de var olmaması gereken paket adları (bkz. CLAUDE.md §3).
FORBIDDEN_DIRS = frozenset(
    {"cloud", "ml", "ui", "coach-ui", "adapters", "edge", "registry", "sync"}
)

# swimcore saftır: I/O yok, duvar saati yok, global rastgelelik yok, ortam kimliği yok.
# Zaman ve kimlik ENJEKTE edilir (ADR-033: Clock, EventIdGenerator).
FORBIDDEN_SWIMCORE_IMPORTS = frozenset(
    {
        "os",
        "io",
        "json",
        "pickle",
        "socket",
        "sqlite3",
        "pathlib",
        "shutil",
        "subprocess",
        "threading",
        "asyncio",
        "logging",
        "random",
        "uuid",
        "time",
        "datetime",
        "secrets",
        "requests",
        "httpx",
        "fastapi",
        "sqlalchemy",
    }
)

# Yasak import'a ek olarak, swimcore içinde ÇAĞRILMASI yasak I/O / non-determinizm built-in'leri.
# (import olmadan da doğrudan çağrılabildikleri için ayrıca AST ile yakalanır — düzeltme #9.)
FORBIDDEN_SWIMCORE_CALLS = frozenset({"open", "input", "eval", "exec", "__import__"})


@dataclass(frozen=True)
class Violation:
    path: Path
    rule: str
    message: str

    def __str__(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{rel}: [{self.rule}] {self.message}"


def check_forbidden_dirs() -> list[Violation]:
    violations: list[Violation] = []
    if not SRC.exists():
        return violations
    for path in SRC.rglob("*"):
        if path.is_dir() and path.name in FORBIDDEN_DIRS:
            violations.append(
                Violation(path, "forbidden-dir", f"'{path.name}/' Faz 1 kapsamı dışında")
            )
    return violations


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def check_swimcore_purity() -> list[Violation]:
    """swimcore hiçbir I/O, saat, rastgelelik veya kimlik kaynağını import edemez."""
    violations: list[Violation] = []
    swimcore = SRC / "swimcore"
    if not swimcore.exists():
        return violations

    for path in sorted(swimcore.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [_root_module(alias.name) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [_root_module(node.module)]
            for name in names:
                if name in FORBIDDEN_SWIMCORE_IMPORTS:
                    violations.append(
                        Violation(
                            path,
                            "swimcore-purity",
                            f"'{name}' import edilemez — swimcore saftır; zaman/kimlik "
                            "Clock ve EventIdGenerator ile enjekte edilir (ADR-033)",
                        )
                    )
            # Doğrudan I/O built-in çağrıları (import gerektirmez).
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in FORBIDDEN_SWIMCORE_CALLS
            ):
                violations.append(
                    Violation(
                        path,
                        "swimcore-purity",
                        f"'{node.func.id}()' cagrilamaz — swimcore saftir, I/O yapmaz (ADR-003)",
                    )
                )
    return violations


def all_violations() -> list[Violation]:
    return check_forbidden_dirs() + check_swimcore_purity()


def main() -> int:
    violations = all_violations()
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        print(f"\n{len(violations)} mimari ihlal.", file=sys.stderr)
        return 1
    print("Mimari uygunluk: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
