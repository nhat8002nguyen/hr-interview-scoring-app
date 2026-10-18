# Build stage: install the workspace dependencies and build the environment.
FROM python:3.14-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY src ./src

RUN uv sync --frozen --no-dev --all-packages

# Runtime stage: carry only the built environment and the source the app needs,
# including the Alembic config and migrations so `alembic upgrade head` works.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "3000"]
