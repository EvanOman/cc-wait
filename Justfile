set shell := ["bash", "-cu"]

default:
    @just --list

fmt:
    uv run ruff format .

format-check:
    uv run ruff format --check .

lint:
    uv run ruff check .

lint-fix:
    uv run ruff check . --fix

type:
    uv run ty check .

test:
    uv run pytest

# FIX + CHECK: Run before every commit
fc: fmt lint-fix lint type test

ci: lint format-check type test

install:
    uv sync --dev

# Redeploy local changes to the running dashboard service
redeploy:
    rm -rf src/cc_wait/__pycache__
    systemctl --user restart cc-wait-dashboard
    @echo "Dashboard restarted. Check: curl -s http://localhost:18800/health"
