# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

# Builds at /app, matching the runtime stage's WORKDIR: `uv sync` bakes an
# absolute shebang (#!/app/.venv/bin/python) into every installed console
# script (alembic, disp, disp-admin, procrastinate, ...). If the two stages'
# paths differ, the copied venv's scripts point at a python that doesn't
# exist in the runtime image, and `exec`-ing any of them fails with "no such
# file or directory" — this was caught by actually running the built image,
# not just building it.
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY README.md ./
# --no-editable: without it, `uv sync` links the venv's disp package back to
# this build stage's /app/src (an editable install) rather than copying it
# in — which breaks at runtime, since the runtime stage's own /app/src is a
# separate copy on a different filesystem layer, not the same inode.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --chown=app:app alembic.ini ./

USER app

EXPOSE 8000

CMD ["uvicorn", "disp.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
