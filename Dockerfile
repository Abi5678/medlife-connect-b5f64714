# =============================================================================
# MedLive Connect — Multi-Stage Docker Build
# Stage 1 (builder): Node 20 → compiles React/TypeScript frontend
# Stage 2 (runtime): Python 3.11 → runs FastAPI + serves compiled frontend
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — Frontend Build
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Dependency layer — cached unless package files change
COPY package.json package-lock.json* ./
# Use npm ci for reproducible installs; fall back to npm install if lock missing
RUN npm ci --prefer-offline 2>/dev/null || npm install

# Copy source files
COPY index.html vite.config.ts tsconfig*.json ./
COPY public/ public/
COPY src/ src/

# Build the React SPA (outputs to /build/dist)
# No VITE_* env vars needed at build time — URLs are resolved at runtime from
# window.location.host (same-origin production) or localhost:8000 (local dev).
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2 — Python Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Python dependency layer — cached until pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application code
COPY agents/ agents/
COPY app/ app/

# React build output from Stage 1 — FastAPI serves this via catch-all route
COPY --from=frontend-builder /build/dist ./dist

# Cloud Run injects PORT; default to 8000
ENV PORT=8000
EXPOSE 8000

# Use uv run so the managed venv is on the path
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
