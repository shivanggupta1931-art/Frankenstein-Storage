"""Main entry point for Frankenstein Storage FastAPI backend."""

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, HTMLResponse, Response

from backend.app.api.endpoints import router
from backend.app.core.config import settings
from backend.app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    validation_error_handler,
)
from backend.app.core.security import SecurityMiddleware
from backend.app.db.connection import get_db
from backend.app.db.migrations import run_migrations
from backend.app.services.storage_engine import startup_cleanup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Run DB migrations
    run_migrations()

    # 2. Startup cleanup of incomplete uploads and orphaned temp files
    with get_db() as conn:
        startup_cleanup(conn)

    # 3. Print session token once to console
    banner = f"""
======================================================================
🧟 FRANKENSTEIN STORAGE BACKEND STARTED
======================================================================
Host:             http://{settings.host}:{settings.port}
Health Endpoint:  http://{settings.host}:{settings.port}/api/v1/health
API Base URL:     http://{settings.host}:{settings.port}/api/v1
SESSION TOKEN:    {settings.session_token}
======================================================================
"""
    sys.stdout.write(banner)
    sys.stdout.flush()

    yield


app = FastAPI(
    title="Frankenstein Storage",
    version="1.0.0",
    description="Pooled Redundant Encrypted Local Storage",
    lifespan=lifespan,
)

# Exception handlers for standard error envelope
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

# Security and Auth middleware
app.add_middleware(SecurityMiddleware)

# Include API endpoints first
app.include_router(router)

# Mount Vite static assets if present
index_file = settings.static_dir / "index.html"
assets_dir = settings.static_dir / "assets"

if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def get_injected_index_html() -> str:
    if not index_file.exists():
        return ""
    raw = index_file.read_text(encoding="utf-8")
    injection = f"""<script>
      window.__FRANKENSTEIN_SESSION_TOKEN__ = "{settings.session_token}";
    </script>
  </head>"""
    if "</head>" in raw:
        return raw.replace("</head>", injection, 1)
    return raw


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa_or_static(full_path: str = ""):
    # If path starts with api/, return 404 to avoid masking API 404s with HTML
    if full_path.startswith("api/"):
        return Response(status_code=404)

    # Check if a direct static file exists in static_dir (e.g. favicon.ico, vite.svg)
    if settings.static_dir.exists():
        if full_path:
            candidate = (settings.static_dir / full_path).resolve()
            try:
                candidate.relative_to(settings.static_dir.resolve())
                if candidate.is_file():
                    return FileResponse(candidate)
            except ValueError:
                pass

        # Otherwise serve SPA index.html with auto-injected session token
        if index_file.exists():
            return HTMLResponse(content=get_injected_index_html())

    # Fallback if no static_dir built
    return {
        "name": "Frankenstein Storage",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


def run():
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
