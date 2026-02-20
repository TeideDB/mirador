# ── Stage 1: Build frontend ──────────────────────────────────────────
FROM node:22-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ .
RUN npm run build

# ── Stage 2: Build Teide native library + Python deps ───────────────
FROM python:3.13-slim AS backend-build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ cmake make git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build Teide from source (C17 engine + Python bindings)
RUN git clone --depth=1 https://github.com/TeideDB/teide-py.git /tmp/teide-py \
    && git clone --depth=1 https://github.com/TeideDB/teide.git /tmp/teide-py/vendor/teide \
    && pip install --no-cache-dir /tmp/teide-py \
    && rm -rf /tmp/teide-py

# Install Mirador Python deps (without the package itself yet)
WORKDIR /app
COPY pyproject.toml .
COPY mirador/__init__.py mirador/__init__.py
RUN pip install --no-cache-dir .

# ── Stage 3: Final runtime image ────────────────────────────────────
FROM python:3.13-slim

# Runtime deps only (libm/pthread are in slim already)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from build stage
COPY --from=backend-build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=backend-build /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application code
COPY mirador/ mirador/

# Copy built frontend into the location FastAPI expects
COPY --from=frontend /build/dist/ mirador/frontend_dist/

# Data directory for persisting projects
RUN mkdir -p /data
ENV MIRADOR_DATA_DIR=/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "mirador.app:app", "--host", "0.0.0.0", "--port", "8000"]
