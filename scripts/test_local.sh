#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

MODE=${1:-"test"}
VENV_DIR=".venv"

function setup_venv() {
    if [ "$MODE" == "clean-test" ]; then
        echo "Cleaning existing virtual environment..."
        rm -rf "$VENV_DIR"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating new virtual environment..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        echo "Installing dependencies..."
        pip install --upgrade pip --quiet
        pip install -e ".[dev]" --quiet
    else
        echo "Using existing virtual environment..."
        source "$VENV_DIR/bin/activate"
    fi
}

echo "Running local validation in mode: $MODE"

setup_venv

# 1. Format check (Black/Ruff)
echo "Checking formatting..."
ruff format --check .

# 2. Linting (Ruff)
echo "Running linter..."
ruff check .

# 3. Type checking (Mypy)
echo "Running type checker..."
mypy src/audiotrace

# 4. Unit tests with coverage
echo "Running unit tests with coverage..."
pytest --cov=audiotrace --cov-report=term-missing --cov-fail-under=95

echo -e "${GREEN}All checks passed!${NC}"
