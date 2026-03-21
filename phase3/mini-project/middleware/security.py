import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import uuid
import time
from fastapi.responses import JSONResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "internal_server_error", "message": str(e)})

        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "frame-ancestors 'none';"
        )
        if "server" in response.headers:
            del response.headers["server"]
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "internal_server_error", "message": str(e)},
                headers={"X-Request-ID": request_id}
            )
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "internal_server_error", "message": str(e)})
        duration = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{duration:.4f}s"
        return response
