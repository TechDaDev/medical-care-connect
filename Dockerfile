# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd --system --gid 1000 django && \
    useradd --system --gid django --uid 1000 --no-create-home django

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY --chown=django:django . .
COPY --chown=django:django entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /app/staticfiles && chown django:django /app/staticfiles && \
    mkdir -p /app/protected_attachments && chown django:django /app/protected_attachments && \
    mkdir -p /app/media/license_documents && chown django:django /app/media/license_documents && \
    chown django:django /app/media

EXPOSE 8000

USER django

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/api/health/'); exit(0)" 2>/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
