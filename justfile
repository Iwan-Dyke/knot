export PATH := justfile_directory() + "/.venv/bin:" + env_var("PATH")
set positional-arguments

test:
    #!/usr/bin/env bash
    set -euo pipefail
    knot_test_root="$(mktemp -d)"
    trap 'rm -rf -- "$knot_test_root"' EXIT
    export KNOT_CONFIG="$knot_test_root/config.json"
    export KNOT_DATA_ROOT="$knot_test_root/data"
    PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v

inventory:
    PYTHONPATH=src .venv/bin/python -m knot.ingestion.inventory

lint:
    ruff check src tests scripts

format:
    ruff format src tests scripts

format-check:
    ruff format --check src tests scripts

check: lint format-check test

# Requires the optional Playwright installation used by the viewer browser tests.
test-idle browser="chromium":
    node scripts/test_library_browser.cjs {{quote(browser)}} --idle-only

# Requires the optional Playwright installation; uses temporary synthetic data.
test-library-authoring browser="chromium":
    node scripts/test_library_authoring.cjs {{quote(browser)}}

migrate:
    PYTHONPATH=src .venv/bin/python -m knot.ingestion.migrate
    PYTHONPATH=src .venv/bin/python -m knot.graph.knowledge build

organise:
    PYTHONPATH=src .venv/bin/python -m knot.graph.knowledge build

knowledge *args:
    PYTHONPATH=src .venv/bin/python -m knot.graph.knowledge "$@"

themes:
    PYTHONPATH=src .venv/bin/python -m knot.graph.knowledge summary

query file="queries/evidence.rq":
    PYTHONPATH=src .venv/bin/python -m knot.graph.query {{quote(file)}}

retrieval +args:
    PYTHONPATH=src .venv/bin/python -m knot.retrieval_engine.service "$@"

notes *args:
    PYTHONPATH=src .venv/bin/python -m knot.interfaces.note_cli "$@"

quality *args:
    PYTHONPATH=src .venv/bin/python -m knot.diagnostics.quality "$@"

curate +args:
    PYTHONPATH=src .venv/bin/python -m knot.curating.candidates "$@"

benchmark-retrieval *args:
    PYTHONPATH=src .venv/bin/python -m knot.diagnostics.benchmark "$@"

mcp *args:
    PYTHONPATH=src .venv/bin/python -m knot.interfaces.mcp_server "$@"

review +args:
    PYTHONPATH=src .venv/bin/python -m knot.reviewing.writer "$@"

visualise *args:
    PYTHONPATH=src .venv/bin/python -m knot.interfaces.view_cli "$@"

browse *args:
    PYTHONPATH=src .venv/bin/python -m knot.presentation.library "$@"

example-data destination:
    PYTHONPATH=src .venv/bin/python scripts/example_data.py {{quote(destination)}}

visualise-theme theme focus="":
    PYTHONPATH=src .venv/bin/python -m knot.presentation.visualise --open --theme {{quote(theme)}} --focus {{quote(focus)}}

visualise-frameworks focus="":
    PYTHONPATH=src .venv/bin/python -m knot.presentation.visualise --frameworks --open --focus {{quote(focus)}}

export-code destination:
    .venv/bin/python scripts/export_code.py {{quote(destination)}}

dataset +args:
    PYTHONPATH=src .venv/bin/python -m knot.interfaces.dataset_cli "$@"
