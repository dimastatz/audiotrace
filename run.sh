#!/bin/bash
# AudioTrace runner script

# Ensure virtual environment is used
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the boot script from its new location
python3 src/audiotrace/boot.py "$@"
