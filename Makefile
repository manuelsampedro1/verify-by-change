.PHONY: test build lint

PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests

build:
	$(PYTHON) -m py_compile verify_by_change.py

lint:
	$(PYTHON) -m py_compile verify_by_change.py
