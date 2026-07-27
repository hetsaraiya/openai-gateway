# syntax=docker/dockerfile:1.7

# ---- builder: resolve and install dependencies into a venv ----------------- #
# The astral uv image is built on python:3.12-slim-bookworm, so the interpreter
# path matches the runtime stage below and the venv is portable between them.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install deps first so this layer caches unless the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- web + Codex CLI -------------------------------------------------------- #
FROM node:22-bookworm-slim AS web-builder

ARG TARGETARCH
ARG CODEX_VERSION=0.145.0

WORKDIR /web
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && case "$TARGETARCH" in \
        amd64) codex_target=x86_64-unknown-linux-musl ;; \
        arm64) codex_target=aarch64-unknown-linux-musl ;; \
        *) echo "Unsupported Codex architecture: $TARGETARCH" >&2; exit 1 ;; \
       esac \
    && curl --fail --location --silent --show-error \
        "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${codex_target}.tar.gz" \
        | tar --extract --gzip --file - --directory /tmp \
    && install --mode=755 "/tmp/codex-${codex_target}" /usr/local/bin/codex \
    && rm -rf /var/lib/apt/lists/*
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web ./
RUN pnpm build


# ---- runtime: minimal image, no uv, non-root ------------------------------- #
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUTH_DIR=/auth \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 gateway \
    && useradd --uid 10001 --gid gateway --create-home gateway

# Copy the prebuilt venv and the application code.
COPY --from=builder --chown=gateway:gateway /app/.venv /app/.venv
COPY --chown=gateway:gateway app ./app
COPY --from=web-builder /usr/local/bin/codex /usr/local/bin/codex
COPY --from=web-builder --chown=gateway:gateway /web/dist ./app/static

# Writable, restricted mount point for the Codex auth.json files. Tokens are
# refreshed and written back here, so it must be read-write at runtime — mount a
# host dir or volume over it (never bake credentials into the image).
RUN install -d -o gateway -g gateway -m 700 /auth
VOLUME ["/auth"]

USER gateway
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
