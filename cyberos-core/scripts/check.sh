#!/usr/bin/env bash
set -euo pipefail

pytest
ruff check .
ruff format --check .
mypy src/cyberos
python -m build --wheel
