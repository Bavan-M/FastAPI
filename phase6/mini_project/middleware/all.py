import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import uuid
from loguru import logger
import time
from fastapi.responses import JSONResponse
from collections import defaultdict,deque

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        request_id=request.headers.get("X-Request-ID",str(uuid.uuid4())[:8])
        
        request.state.request_id=request_id
        with logger.contextualize(request_id=request_id):
            response=await call_next(request)
        response.headers["X-Request-ID"]=request_id
        return response
    
class LoggingMiddleware(BaseHTTPMiddleware):
    SKIP={"/health","/ready","/metrics"}

    async def dispatch(self, request:Request, call_next):
        if request.url.path in self.SKIP:
            return await call_next(request)
        
        request_id=getattr(request.state,"request_id","unknown")
        start=time.perf_counter()
        with logger.contextualize(request_id=request_id):
            logger.bind(
                method=request.method,
                path=request.url.path,
                event="request_start"
            ).info(f"-> {request.method}{request.url.path}")
        try:
            response=await call_next(request)
            duration=(time.perf_counter()-start)*1000
            log_fn=logger.warning if response.status_code>=400 else logger.info
            logger.bind(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration),
                event="request_complete"
            ).info(f"<- {response.status_code}({round(duration)}ms)")
            response.headers["X-Process-Time"]=f"{duration:.2f}ms"
            return response
        except Exception as e:
            logger.bind(
                path=request.url.path,
                error=str(e),
                event="request_error"
            ).exception("Unhandled exception")
            raise

class RateLimitMiddleware(BaseHTTPMiddleware):
    SKIP = {"/health", "/ready", "/metrics", "/docs", "/openapi.json"}

    def __init__(self, app, limit: int = 60, window: int = 60):
        super().__init__(app)
        self.limit   = limit
        self.window  = window
        self._windows: dict = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.SKIP:
            return await call_next(request)

        ip  = request.client.host if request.client else "unknown"
        now = time.monotonic()

        window = self._windows[ip]
        cutoff = now - self.window
        while window and window[0] <= cutoff:
            window.popleft()

        remaining = self.limit - len(window)

        if len(window) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error":       "rate_limit_exceeded",
                    "retry_after": self.window
                },
                headers={
                    "X-RateLimit-Limit":     str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After":           str(self.window)
                }
            )

        window.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"]     = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        return response
    

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "frame-ancestors 'none';"
        )
        return response