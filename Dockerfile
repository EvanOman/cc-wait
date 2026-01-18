FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev

# Default environment
ENV PORT=8000
ENV HOST=0.0.0.0
ENV OTEL_ENABLED=true
ENV OTEL_EXPORTER_ENDPOINT=http://host.docker.internal:4317

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the server
CMD ["uv", "run", "cc-wait-server"]
