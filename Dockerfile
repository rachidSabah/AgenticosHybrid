# Agentic OS — runtime image (Python 3.14+, local-first, containerized)
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# Install uv (pinned major) for reproducible, fast installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy source.
COPY src ./src
COPY docs ./docs

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# `serve` runs the orchestrator kernel + FastAPI control plane.
CMD ["python", "-m", "agentic_os", "serve"]
