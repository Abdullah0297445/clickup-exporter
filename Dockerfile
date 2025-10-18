FROM python:3.14-slim-trixie

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.0 /uv /uvx /bin/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY ./scripts/run_command /run_command
RUN chmod +x /run_command
COPY ./scripts/celery/beat/start /start_beat
RUN chmod +x /start_beat
COPY ./scripts/celery/flower/start /start_flower
RUN chmod +x /start_flower
COPY ./scripts/celery/worker/start /start_worker
RUN chmod +x /start_worker
COPY ./scripts/start /start
RUN chmod +x /start
COPY ./pyproject.toml ./uv.lock /app/
COPY ./apps /app/apps

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
