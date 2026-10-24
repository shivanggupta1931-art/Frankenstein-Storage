"""Security middleware: Host, Origin, and Bearer Token enforcement."""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.core.config import settings


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Host Validation
        host = request.headers.get("host", "").lower().strip()
        if host and not settings.allow_all_hosts:
            base_host = host.split(":")[0]
            if base_host not in settings.allowed_hosts and host not in settings.allowed_hosts:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": f"Forbidden host header: '{host}'. Only permitted hosts are allowed.",
                            "details": {},
                        }
                    },
                )

        # 2. Origin Validation (for browser requests)
        origin = request.headers.get("origin")
        origin_allowed = False
        if origin:
            clean_origin = origin.lower().strip()
            if settings.allow_all_origins:
                origin_allowed = True
            else:
                is_loopback = (
                    clean_origin.startswith("http://127.0.0.1:")
                    or clean_origin.startswith("http://localhost:")
                    or clean_origin.startswith("https://127.0.0.1:")
                    or clean_origin.startswith("https://localhost:")
                    or clean_origin in {"http://127.0.0.1", "http://localhost", "http://testserver"}
                )
                # Allow all Vercel preview and production domains (*.vercel.app, *.now.sh, *.tmp.now)
                is_vercel = clean_origin.startswith("https://") and (
                    clean_origin.endswith(".vercel.app")
                    or clean_origin.endswith(".now.sh")
                    or clean_origin.endswith(".tmp.now")
                    or clean_origin == "https://vercel.app"
                )
                if (
                    is_loopback
                    or is_vercel
                    or clean_origin in settings.allowed_origins
                    or clean_origin.rstrip("/") in settings.allowed_origins
                ):
                    origin_allowed = True

            if not origin_allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": f"Forbidden origin: '{origin}'. Only permitted origins are allowed.",
                            "details": {},
                        }
                    },
                )

        cors_headers: dict[str, str] = {}
        if origin and (origin_allowed or settings.allow_all_origins):
            cors_headers["Access-Control-Allow-Origin"] = origin
            cors_headers["Access-Control-Allow-Credentials"] = "true"

        # Handle CORS Preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = Response(status_code=204)
            if origin and (origin_allowed or settings.allow_all_origins):
                response.headers["Access-Control-Allow-Origin"] = origin
            else:
                response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, Content-Disposition, X-File-SHA256, X-Rebuilt-From-Parity"
            )
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = (
                "Content-Disposition, Content-Length, X-File-SHA256, X-Rebuilt-From-Parity"
            )
            return response

        # 3. Path whitelist for auth
        path = request.url.path
        if not path.startswith("/api/"):
            # Static files, SPA pages, frontend assets
            response = await call_next(request)
            for k, v in cors_headers.items():
                response.headers[k] = v
            return response

        if path in {"/api/v1/health", "/health", "/docs", "/openapi.json"}:
            response = await call_next(request)
            for k, v in cors_headers.items():
                response.headers[k] = v
            return response

        # 4. Bearer Token Auth
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "token" in request.query_params:
            token = request.query_params.get("token", "").strip()

        if not token:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authorization header missing or not Bearer token",
                        "details": {},
                    }
                },
                headers=cors_headers,
            )

        if not hmac.compare_digest(token, settings.session_token):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid session authorization token",
                        "details": {},
                    }
                },
                headers=cors_headers,
            )

        response = await call_next(request)
        for k, v in cors_headers.items():
            response.headers[k] = v
        response.headers["Access-Control-Expose-Headers"] = (
            "Content-Disposition, Content-Length, X-File-SHA256, X-Rebuilt-From-Parity"
        )
        return response
