# FormulaForge API — container image for the FastAPI service.
#
# Build context is backend/ (that is where .dockerignore must live for Docker to
# read it):
#   docker build -t formulaforge-api ./backend
#
# ── Build stage ───────────────────────────────────────────────────────────────
# Pinned to an exact patch release matching .python-version / runtime.txt, not
# `latest`: requirements.txt pins every dependency to an exact version, and a
# floating interpreter would undo that reproducibility from underneath. For a
# fully immutable pin, append the digest:
#   FROM python:3.11.9-slim-bookworm@sha256:<digest> AS builder
FROM python:3.11.9-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencies are installed into a self-contained venv that the runtime stage
# copies wholesale, so pip, its metadata, and the wheel cache never reach the
# shipped image. requirements.txt is copied on its own so this layer is rebuilt
# only when the pinned dependency set changes — not on every source edit.
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11.9-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root, with a fixed uid/gid so the identity stays stable across base-image
# bumps and is legible to image scanners.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Application code last: it changes most often, so it invalidates the fewest
# layers. Deliberately left root-owned — the service only ever reads its own
# code (PYTHONDONTWRITEBYTECODE keeps .pyc out of /app), so appuser has no write
# access to the application it is running.
COPY . /app

USER appuser

# Documentation only; the port actually served is whatever $PORT resolves to.
EXPOSE 8000

# Readiness probe against the /health endpoint (main.py). Uses the venv's own
# interpreter so the image needs no curl or wget: urllib raises on the 503 that
# /health returns when a critical dependency is unavailable, which exits non-zero.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)"]

# Bind 0.0.0.0 and read $PORT so one image runs identically locally and on
# Render. Shell form with exec: uvicorn replaces the shell as PID 1 and so
# receives SIGTERM directly on shutdown.
#
# No secrets are baked in. GROQ_API_KEY, ALLOWED_ORIGINS, and the rest are
# supplied at runtime (see backend/.env.example).
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
