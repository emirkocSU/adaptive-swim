.PHONY: setup lint typecheck test test-unit test-property test-replay test-simulator \
        test-architecture arch-check schema-check e2e-headless ci

export PYTHONPATH := $(CURDIR)/src

PY := python
PYTEST := $(PY) -m pytest

setup:
	$(PY) -m venv .venv && .venv/bin/pip install -e ".[dev]"

lint:
	ruff check src tests && ruff format --check src tests

typecheck:
	mypy --strict src

test:
	$(PYTEST) -q

test-unit:
	$(PYTEST) -q tests/unit

# --- The targets below become active in later commits. Until a test dir has ---
# --- tests, they print PENDING and succeed so `make ci` stays green.        ---
test-property:
	@if ls tests/property/test_*.py >/dev/null 2>&1; then \
		$(PYTEST) -q tests/property ; \
	else echo "PENDING (property tests arrive in a later commit)"; fi

test-replay:
	$(PYTEST) -q tests/replay --disable-socket

test-simulator:
	$(PYTEST) -q tests/simulator --disable-socket

test-architecture:
	lint-imports && $(PYTEST) -q tests/architecture

arch-check:
	$(PY) -m swimtools.arch_check

schema-check:
	$(PY) -m swimtools.gen_schemas --check

e2e-headless:
	@if ls tests/e2e/test_*.py >/dev/null 2>&1; then \
		$(PYTEST) -q tests/e2e --disable-socket ; \
	else echo "PENDING (e2e headless vertical slice arrives in Commit 10)"; fi

ci: lint typecheck test-architecture arch-check schema-check test-unit test-property test-replay test-simulator e2e-headless
	@echo "CI OK"
