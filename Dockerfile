# ── Stage 1: Build frontend ──
FROM node:22-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
ARG VITE_SUPABASE_URL=https://supabase.intecha.dev
ARG VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_eOn6jCKOJYVPzRh39CQIFJ_0zYEU4iV
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
RUN npm run build

# ── Stage 2: Build backend + runtime ──
FROM python:3.12-slim

WORKDIR /app

# Runtime dependencies (minimi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Backend Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY backend/ .

# Frontend build (dallo stage 1)
COPY --from=frontend-builder /app/dist /app/static

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
