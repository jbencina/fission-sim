# Makefile — fission-sim development convenience targets
#
# Prerequisites
# -------------
#   uv  (Python / virtualenv management)
#   npm (Node.js package management, for the Vite frontend)
#
# First-time setup
# ----------------
#   make install
#
# Daily use
# ---------
#   make dev      — start both the FastAPI backend and Vite frontend
#   make api      — backend only
#   make web      — frontend only

.PHONY: dev api web install install-e2e e2e test lint

## Start both the FastAPI backend (port 8000) and the Vite frontend (port 5173)
## concurrently, with coloured prefixed output.  Press Ctrl-C to stop both.
##
## Implementation note: ``uv sync`` is run first to ensure the virtualenv
## exists, then ``exec`` replaces the recipe shell with the Python interpreter
## directly so that the launcher receives terminal Ctrl-C in normal interactive
## use. The launcher also watches for parent-process death so harness teardown
## can still clean up both child servers.
dev:
	uv sync --quiet && exec .venv/bin/python scripts/dev.py

## Start only the FastAPI / uvicorn backend.
api:
	uv run python -m fission_sim.api

## Start only the Vite dev server.
web:
	npm run dev --prefix web

## Install all Python and Node.js dependencies (run once after cloning).
install:
	uv sync && npm install --prefix web

## Install the Chromium browser used by the Playwright smoke test.
install-e2e:
	npm exec --prefix web -- playwright install chromium

## Run the Playwright smoke test against an already-running make dev stack.
e2e:
	npm run e2e --prefix web

## Run the full test suite (Python + JavaScript).
test:
	uv run pytest && npm run test --prefix web -- --run

## Lint both the Python package and the frontend.
lint:
	uv run ruff check src tests && npm run lint --prefix web
