# The API image (Lane P): the plumbline package and its runtime dependencies, nothing else.
# Build it from the repository root, which the uv workspace needs as the context:
#
#   docker build -f deploy/api/Dockerfile -t plumbline-api .
#
# Settings come from the environment (production Compose passes them from a root-only
# file); data/ and cache/ are mounted read-only under /app. The Dubai PDFs are fetched on
# the server and never committed, so they never end up inside an image either.
#
# Two stages on the same pinned base, because the virtual environment links to that
# image's Python: uv builds a non-editable environment from uv.lock, and the final stage
# copies only that environment, the migrations and the answer configurations, and runs
# unprivileged. Dependabot refreshes the pinned digests.

FROM ghcr.io/astral-sh/uv:0.13.3@sha256:bee0a2a458fd956c5df7b8b4c5fed2257b0af34866e3da7b51db0be3acb375d1 AS uv

FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
COPY --from=uv /uv /bin/uv
# Bytecode is compiled here because the runtime filesystem is read-only; files are copied
# out of the cache mount rather than linked; only the base image's Python is used.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Third-party dependencies first, in a layer that changes only when the lock does. This
# sync is --frozen because the members' sources are not there yet; the next one checks
# the lock with --locked.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=apps/api/pyproject.toml,target=apps/api/pyproject.toml \
    --mount=type=bind,source=packages/rag-eval/pyproject.toml,target=packages/rag-eval/pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --package plumbline
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
COPY apps/api/src apps/api/src
COPY packages/rag-eval packages/rag-eval
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package plumbline

FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
LABEL org.opencontainers.image.title="plumbline-api" \
      org.opencontainers.image.source="https://github.com/alined-labs/plumbline" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd --system --gid 10001 plumbline \
 && useradd --system --uid 10001 --gid plumbline --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin plumbline
WORKDIR /app
# Everything stays owned by root: the service can read its code, never change it.
COPY --from=build /app/.venv /app/.venv
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/migrations apps/api/migrations
COPY evals/configs evals/configs
# The package is installed into site-packages, so PLUMBLINE_ROOT tells the settings where
# evals/, data/ and cache/ live.
ENV PATH="/app/.venv/bin:$PATH" \
    PLUMBLINE_ROOT=/app \
    ENVIRONMENT=prod \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --start-interval=1s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]
# Shutdown ends open answer streams before Docker's 10-second stop timeout. Forwarded
# headers are trusted only from FORWARDED_ALLOW_IPS (default 127.0.0.1); production
# Compose sets it to the tunnel's address so per-IP quotas see the visitor's address.
CMD ["uvicorn", "plumbline.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--timeout-graceful-shutdown", "8"]
