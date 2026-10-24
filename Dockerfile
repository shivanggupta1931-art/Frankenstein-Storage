# ========================================================
# Stage 1: Build Frontend Assets (Vite + React + Tailwind)
# ========================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ========================================================
# Stage 2: Production Python Server
# ========================================================
FROM python:3.12-slim AS runner

# Performance & environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8765 \
    ALLOW_ALL_HOSTS=true \
    STATIC_DIR=/app/frontend/dist \
    DATABASE_PATH=/data/frankenstein.db

# Install runtime utilities (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install backend dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend ./backend
COPY pyproject.toml ./

# Copy pre-compiled Vite frontend bundle from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create storage mounts
RUN mkdir -p /data /mnt/storage
VOLUME ["/data"]

EXPOSE 8765

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/api/v1/health || exit 1

# Start unified single-port production server
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
