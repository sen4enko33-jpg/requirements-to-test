# make run   - both parts, one command each (see the READMEs); make run1 / make run2 - one part; make test - all tests (no network, no key)
PYTHON ?= python3

.PHONY: run run1 run2 test
run: run1 run2

run1:
	cd task1-extraction && $(PYTHON) main.py

run2:
	cd task2-rag && $(PYTHON) main.py

test:
	cd task1-extraction && for t in tests/test_*.py; do $(PYTHON) $$t || exit 1; done
	cd task2-rag && for t in tests/test_*.py; do $(PYTHON) $$t || exit 1; done
