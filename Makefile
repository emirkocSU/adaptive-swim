.PHONY: setup lint format typecheck test test-unit test-property test-replay test-simulator \
        test-architecture schema-check e2e-headless ci clean

PY := python
VENV := .venv

# Test suites arrive commit by commit (see docs/plan/first-10-commits.md).
# Targets whose directory does not exist yet are reported as PENDING rather than
# failing, so that `make ci` is green at the end of every single commit.
define run_suite
	@if [ -d "$(1)" ]; then \
		pytest $(1) $(2); \
	else \
		echo "PENDING: $(1) (arrives in a later Phase 1 commit)"; \
	fi
endef

setup:
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

format:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy

test:
	pytest

test-unit:
	$(call run_suite,tests/unit,)

test-property:
	$(call run_suite,tests/property,--hypothesis-profile=ci)

test-replay:
	$(call run_suite,tests/replay,)

test-simulator:
	$(call run_suite,tests/simulator,)

test-architecture:
	lint-imports --config .importlinter
	$(call run_suite,tests/architecture,)

# Regenerates JSON Schema from pydantic and fails if the committed schema differs.
# Becomes active in Commit 2, when contracts and the generator exist.
schema-check:
	@if [ -f src/swimtools/gen_schemas.py ]; then \
		$(PY) -m swimtools.gen_schemas --check; \
	else \
		echo "PENDING: schema generator (arrives in Commit 2)"; \
	fi

e2e-headless:
	$(call run_suite,tests/e2e,--disable-socket)

# Single-command Phase 1 verification.
ci: lint typecheck test-architecture schema-check test-unit test-property test-replay test-simulator e2e-headless

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis out
