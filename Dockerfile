# Build the web UI
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN mkdir -p ../src/shortstock && npm run build

# Runtime: Python + ffmpeg (with libass for captions)
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
COPY --from=web /app/src/shortstock/web src/shortstock/web
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" \
    SHORTSTOCK_HOME=/data
VOLUME /data
EXPOSE 8000
CMD ["shortstock", "serve", "--host", "0.0.0.0", "--port", "8000"]
