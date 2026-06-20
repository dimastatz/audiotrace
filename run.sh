#!/bin/bash
# AudioTrace runner script
#
# Usage:
#   ./run.sh [audio_file] [--animate]
#
#   audio_file     Path to an audio file (default: bundled Paradise Hotel demo).
#   -a, --animate  Play the audio and animate the transcript word by word.
#
# Examples:
#   ./run.sh                                # analyze the demo fixture
#   ./run.sh --animate                      # animated demo with audio
#   ./run.sh path/to/call.mp3 --animate     # animate your own file

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
python3 -c "import whisper" 2>/dev/null || MISSING_DEPS+=("openai-whisper")
python3 -c "import pyannote.audio" 2>/dev/null || MISSING_DEPS+=("pyannote.audio")

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

# 3. Helpful first-run hints
echo -e "${GREEN}AudioTrace${NC} — first run downloads the local models (Whisper, sentiment, intent); cached afterwards."
if [ -z "${HF_TOKEN:-}" ]; then
    echo "Tip: set HF_TOKEN to enable real pyannote diarization (otherwise speakers are inferred by pitch)."
fi

# 4. Run (forwards the file path and flags such as --animate to the CLI)
python3 src/audiotrace/boot.py "$@"
