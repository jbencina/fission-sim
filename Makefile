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

.PHONY: dev api web install test lint

## Start both the FastAPI backend (port 8000) and the Vite frontend (port 5173)
## concurrently, with coloured prefixed output.  Press Ctrl-C to stop both.
##
## Implementation note: ``uv sync`` is run first to ensure the virtualenv
## exists, then ``exec`` replaces the recipe shell with the Python interpreter
## directly so that the Python process is the immediate child of Make.  This
## ensures that SIGINT propagates cleanly (Make sends SIGINT to its child when
## Make itself receives SIGINT), which matters when running in a non-interactive
## context such as a test harness using ``kill -INT $MAKE_PID``.
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

## Run the full test suite (Python + JavaScript).
test:
	uv run pytest && npm run test --prefix web -- --run

## Lint both the Python package and the frontend.
lint:
	uv run ruff check src tests && npm run lint --prefix web
