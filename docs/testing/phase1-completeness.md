# Phase 1 completeness check

Phase 1 may not claim a green CI result by conditionally skipping a missing suite. The
mechanical gate is implemented at:

```text
src/swimtools/completeness_check.py
```

and is exposed as:

```bash
make phase1-completeness
```

The command checks repository completeness only; it does **not** execute the test suite.
`make ci` depends on this gate and then runs the real validation commands.

## Mechanical rules

1. `tests/unit`, `tests/property`, `tests/replay`, `tests/simulator`, `tests/analytics`,
   `tests/architecture` and `tests/e2e` all exist and contain a `test_*.py` file.
2. `src/swimtools/gen_schemas.py` and `src/swimtools/completeness_check.py` exist.
3. Makefile contains no `PENDING` fallback or message.
4. `phase1-completeness` exists and `ci` depends on it.
5. `test-property` runs pytest directly rather than conditionally returning success.
6. pytest marker names are unique.
7. `docs/testing/invariants.md` contains exactly I-P1-01 through I-P1-20 closure bindings.
8. Every binding resolves to an existing Python file and an actual top-level test function.

## Current Phase 1 closure

The former Commit 8/9 passages that described E2E or Commit 10 as pending were historical
status reports and are not the state of this repository. The implemented closure includes:

- atomic aggregate rollback including runtime reference identity;
- append-only journal and historical replay;
- deterministic simulator and analytics;
- canonical E2E bundles with recomputed run/report/manifest identities;
- full payload binding for command outcomes and optional observations;
- real Workout 1.0 migration inside the legacy case;
- dual-session legacy/migrated profile equivalence;
- the twenty mechanically resolvable invariant bindings.

The package status is `READY_FOR_OPERATOR_VALIDATION`, not a claim that tests were run by the
packager. The operator must execute:

```bash
python -m pip install -e ".[dev]"
make phase1-completeness
make ci
```

## Deliberate scope boundary

Real multi-hundred-megabyte dataset bundles remain an operator validation step and are not
embedded as fixtures, because raw data is excluded from the repository. Coach UI, cloud,
device drivers, live wearable integration and production ML also remain outside Phase 1.
