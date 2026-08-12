# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS web-build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ARG INSTALL_AI=1
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CINEVOICE_DATA_DIR=/app/data/jobs \
    CINEVOICE_FRONTEND_DIR=/app/frontend \
    CINEVOICE_REQUIRE_AI=0

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libsndfile1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src
RUN python -m pip install --upgrade pip \
    && python -m pip install /app/backend

ARG DEEPFILTER_VERSION=0.5.6
ARG DEEPFILTER_SHA256=70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da
RUN if [ "$INSTALL_AI" = "1" ] && [ "$(uname -m)" = "x86_64" ]; then \
      curl -fsSL \
        "https://github.com/Rikorose/DeepFilterNet/releases/download/v${DEEPFILTER_VERSION}/deep-filter-${DEEPFILTER_VERSION}-x86_64-unknown-linux-musl" \
        -o /usr/local/bin/deep-filter \
      && echo "${DEEPFILTER_SHA256}  /usr/local/bin/deep-filter" | sha256sum -c - \
      && chmod 0755 /usr/local/bin/deep-filter \
      && /usr/local/bin/deep-filter --version; \
    elif [ "$INSTALL_AI" = "1" ]; then \
      echo "DeepFilterNet standalone binary is unavailable for $(uname -m); building without AI"; \
    fi

COPY --from=web-build /web/dist /app/frontend
RUN useradd --create-home --uid 10001 cinevoice \
    && mkdir -p /app/data/jobs \
    && chown -R cinevoice:cinevoice /app/data
USER cinevoice

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["uvicorn", "cinevoice_api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-server-header"]
