#!/bin/bash
# AudioTrace runner script

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m'

# 1. Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 2. Dependency Validation
MISSING_DEPS=()
python3 -c "import pydantic" 2>/dev/null || MISSING_DEPS+=("pydantic")
python3 -c "import rich" 2>/dev/null || MISSING_DEPS+=("rich")

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo "Missing dependencies: ${MISSING_DEPS[*]}"
    echo -n "Would you like to install the package and its dependencies now? (y/n) "
    read -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Install the package in editable mode using pyproject.toml
        pip install -e .
    else
        echo "Please install dependencies manually or run: pip install -e ."
        exit 1
    fi
fi

# 3. Run
python3 src/audiotrace/boot.py "$@"
