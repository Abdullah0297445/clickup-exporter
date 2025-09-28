FROM python:3.13-slim-trixie

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY ./pyproject.toml ./uv.lock /app/
COPY app /app/app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

CMD uv run --no-default-groups --directory ./app fastapi run main.py --port ${FASTAPI_PORT}
