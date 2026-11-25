# Backend image for Railway. BUILD CONTEXT = repository root (see /railway.toml and /.dockerignore):
#   docker build -f backend/Dockerfile -t digiyatra-backend .
# Ships only backend code + the approved deployment corpus (knowledge/deploy). Never knowledge/raw or curated.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    KNOWLEDGE_CORPUS_DIR=/app/knowledge/deploy \
    INDEX_DIR=/data/lancedb \
    EMBEDDING_PROVIDER=lexical \
    PORT=8000

WORKDIR /app/backend

COPY backend/requirements.lock ./requirements.lock
RUN pip install -r requirements.lock

COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
COPY backend/ingestion ./ingestion
COPY backend/app ./app
COPY backend/scripts/start.sh ./scripts/start.sh
COPY backend/scripts/sync.sh ./scripts/sync.sh
COPY knowledge/deploy /app/knowledge/deploy

# Unprivileged runtime user; /data holds the (rebuildable) LanceDB index — mount a Railway volume here
# to skip the ~seconds rebuild on restart, or leave it ephemeral (ensure-index rebuilds deterministically).
RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /data/lancedb \
    && chown -R app:app /app /data \
    && chmod +x ./scripts/start.sh ./scripts/sync.sh
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health', timeout=4)" || exit 1

CMD ["./scripts/start.sh"]
