"""Main entry point for Frankenstein Storage FastAPI backend."""

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

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

# Include API endpoints
app.include_router(router)


def run():
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
