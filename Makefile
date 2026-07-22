.PHONY: setup lint typecheck test test-unit test-property test-replay test-simulator \
        test-analytics test-e2e test-architecture arch-check schema-check \
        phase1-completeness e2e-headless ci

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

test-property:
	$(PYTEST) -q tests/property

test-replay:
	$(PYTEST) -q tests/replay --disable-socket

test-simulator:
	$(PYTEST) -q tests/simulator --disable-socket

test-analytics:
	$(PYTEST) -q tests/analytics --disable-socket

test-e2e:
	$(PYTEST) -q tests/e2e --disable-socket

test-architecture:
	lint-imports && $(PYTEST) -q tests/architecture

arch-check:
	$(PY) -m swimtools.arch_check

schema-check:
	$(PY) -m swimtools.gen_schemas --check

phase1-completeness:
	$(PY) -m swimtools.completeness_check

# Full Phase 1 vertical slice through the real CLIs, then byte-level bundle verification.
e2e-headless:
	$(PY) -m swimtools.run_e2e --all --output .phase1-e2e
	$(PY) -m swimtools.verify_e2e_bundle --bundle .phase1-e2e --recursive
	rm -rf .phase1-e2e

ci: phase1-completeness lint typecheck test-architecture arch-check schema-check \
    test-unit test-property test-replay test-simulator test-analytics test-e2e e2e-headless
	@echo "CI OK"
