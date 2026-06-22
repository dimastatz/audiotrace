# AudioTrace CLI Application Dockerfile
#   Build:  docker build -f docker/Dockerfile -t audiotrace .
#   Run:    docker run -it audiotrace [file_path]

FROM python:3.12-slim-bookworm

# Install FFmpeg (system dependency for audio processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy packaging files first for better layer caching
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Install the package and dependencies
# We install in non-editable mode for the production-like container
RUN pip install --no-cache-dir .

# Copy the rest of the files (tests for golden data, runner script)
COPY tests/fixtures ./tests/fixtures
COPY scripts/run.sh ./scripts/run.sh

# Ensure the runner is executable
RUN chmod +x scripts/run.sh

# Set the entrypoint to the runner script
# Since we pre-install dependencies above, run.sh will bypass the
# interactive prompt and start analysis immediately.
ENTRYPOINT ["./scripts/run.sh"]
