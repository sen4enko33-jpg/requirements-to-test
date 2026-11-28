# make run   - all three parts, one command each (see the READMEs); make run1 / run2 / run3 - one part;
# make run3 Q="your question" - the agent of task 3 on any question; make test - all tests (no network, no key)
PYTHON ?= python3

.PHONY: run run1 run2 run3 test
run: run1 run2 run3

Q ?= How many days a week can employees work remotely?

run1:
	cd task1-extraction && $(PYTHON) main.py

run2:
	cd task2-rag && $(PYTHON) main.py

run3:
	cd task3-agent && $(PYTHON) main.py "$(Q)"

test:
	cd task1-extraction && for t in tests/test_*.py; do $(PYTHON) $$t || exit 1; done
	cd task2-rag && for t in tests/test_*.py; do $(PYTHON) $$t || exit 1; done
	cd task3-agent && for t in tests/test_*.py; do $(PYTHON) $$t || exit 1; done
