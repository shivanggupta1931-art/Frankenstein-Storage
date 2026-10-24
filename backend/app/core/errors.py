"""Standardized Frankenstein Storage Error Envelope and Exceptions.

Errors use one envelope: {"error": {"code": str, "message": str, "details": any}}
"""

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def format_error_response(
    status_code: int, code: str, message: str, details: Any | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return format_error_response(exc.status_code, exc.code, exc.message, exc.details)


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        503: "SERVICE_UNAVAILABLE",
        507: "INSUFFICIENT_STORAGE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    return format_error_response(exc.status_code, code, str(exc.detail))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return format_error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        "Request validation failed",
        exc.errors(),
    )
