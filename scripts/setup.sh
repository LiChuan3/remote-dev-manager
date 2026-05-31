#!/usr/bin/env bash
# setup.sh - Set up development environment for remote-dev-manager
# Usage: ./scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# --- Detect Python 3.10+ ---
PYTHON_CMD=""

for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '(?<=Python 3\.)\d+' || true)
        if [ -n "$ver" ] && [ "$ver" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            echo "[OK] Found: $("$cmd" --version 2>&1)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.10+ is required but not found." >&2
    echo "Install from https://www.python.org/downloads/" >&2
    exit 1
fi

# --- Create venv ---
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "[OK] Virtual environment created."
else
    echo "[OK] Virtual environment already exists."
fi

# --- Activate and install ---
source "$VENV_DIR/bin/activate"

echo "Installing package in editable mode ..."
pip install -e ".[dev]"

# --- Done ---
echo ""
echo "========================================"
echo " Setup complete!"
echo "========================================"
echo ""
echo "Activate the venv:"
echo "  source .venv/bin/activate"
echo ""
echo "Run rdm:"
echo "  rdm --help"
echo "  rdm tui"
