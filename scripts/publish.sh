#!/bin/bash
set -e

# Build the AudioTrace package and upload it to PyPI.
#
# Usage:
#   ./scripts/publish.sh [--test] [--skip-tests]
#
#   --test        Upload to TestPyPI instead of the real PyPI.
#   --skip-tests  Skip the local validation suite before building.
#
# Authentication (twine): configure ~/.pypirc, or export
#   TWINE_USERNAME=__token__
#   TWINE_PASSWORD=<your-api-token>
# See https://pypi.org/help/#apitoken for creating an API token.

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

REPO="pypi"
RUN_TESTS=1
for arg in "$@"; do
    case "$arg" in
        --test) REPO="testpypi" ;;
        --skip-tests) RUN_TESTS=0 ;;
        *) echo -e "${RED}Unknown option: $arg${NC}"; exit 1 ;;
    esac
done

VENV_DIR=".venv"

# 1. Virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip --quiet
    pip install -e ".[dev]" --quiet
else
    echo "Using existing virtual environment..."
    source "$VENV_DIR/bin/activate"
fi

# 2. Build/upload tooling
echo "Ensuring build tooling (build, twine)..."
pip install --upgrade build twine --quiet

# 3. Validation gate (Definition of Done: keep CI green)
if [ "$RUN_TESTS" -eq 1 ]; then
    echo "Running validation suite..."
    ./scripts/test_local.sh test
else
    echo -e "${YELLOW}Skipping validation suite (--skip-tests).${NC}"
fi

# 4. Clean previous artifacts
echo "Cleaning old build artifacts..."
rm -rf dist build ./*.egg-info src/*.egg-info

# 5. Build sdist + wheel
echo "Building package..."
python -m build

# 6. Validate the artifacts
echo "Checking artifacts with twine..."
twine check dist/*

# 7. Confirm and upload
VERSION=$(grep -m1 '^version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')
echo -e "${YELLOW}About to upload audiotrace ${VERSION} to ${REPO}.${NC}"
ls -1 dist
read -p "Continue with upload? (y/N) " -n 1 -r
echo
if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Aborted. Built artifacts are in ./dist."
    exit 0
fi

echo "Uploading to ${REPO}..."
if [ "$REPO" == "testpypi" ]; then
    twine upload --repository-url https://test.pypi.org/legacy/ dist/*
else
    twine upload dist/*
fi

echo -e "${GREEN}Published audiotrace ${VERSION} to ${REPO}.${NC}"
