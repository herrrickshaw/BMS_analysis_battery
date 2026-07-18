# Makefile -- reusable entry points for the dev-tooling stack in pyproject.toml.
# Run `make help` for the list. Install the tools first with `make install-dev`.
#
# Design: `format`/`lint` are the two you run locally and they WRITE changes.
# Everything else (lint-check/typecheck/security/duplicates) is report-only --
# safe to run any time, never touches your files.

.PHONY: help install-dev format lint lint-check typecheck security duplicates duplicates-jscpd check-all

help:
	@echo "install-dev       pip install the pinned tool versions (requirements-dev.txt)"
	@echo "format            ruff format .                (writes)"
	@echo "lint              ruff check --fix .            (writes)"
	@echo "lint-check        ruff check .                  (report only)"
	@echo "typecheck         mypy .                         (report only)"
	@echo "security          bandit -r .                    (report only)"
	@echo "duplicates        pylint --enable=duplicate-code  (report only, AST-aware)"
	@echo "duplicates-jscpd  jscpd .                         (report only, token-based, needs npx)"
	@echo "check-all         lint-check + typecheck + security + duplicates, no writes"

install-dev:
	pip install -r requirements-dev.txt

format:
	ruff format .

lint:
	ruff check --fix .

lint-check:
	ruff check .

typecheck:
	mypy .

security:
	bandit -r . -c pyproject.toml

duplicates:
	pylint --disable=all --enable=duplicate-code $$(git ls-files '*.py')

duplicates-jscpd:
	npx --yes jscpd@latest . --min-lines 10 --min-tokens 70 \
		--ignore "**/cache_seed/**,**/docs_cache/**,**/*.ipynb"

check-all: lint-check typecheck security duplicates
	@echo "Done -- report-only, nothing written. Run 'make format' / 'make lint' to fix what's auto-fixable."
