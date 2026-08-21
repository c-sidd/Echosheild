# EchoShield backend — production-quality image
# Multi-stage build: uv resolves locked dependencies, runtime stays slim.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Final venv path up-front so console-script shebangs stay valid in runtime.
WORKDIR /app

# Dependency layer first (cached until lockfile changes).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Application layer.
COPY app ./app
RUN uv sync --frozen --no-dev


FROM python:3.12-slim

LABEL org.opencontainers.image.title="echoshield-backend"
LABEL org.opencontainers.image.description="FastAPI application API for the EchoShield ocean-data platform"

RUN groupadd --system echoshield && useradd --system --gid echoshield echoshield

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER echoshield

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
