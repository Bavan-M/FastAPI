import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import uuid
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from core.config import settings
from core.logging import setup_logging, logger, api_logger
from core.telemetry import setup_telemetry
from middleware.all import (
    RequestIDMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware
)
from routers import auth, items, llm


# ============================================================
# TELEMETRY — initialize before app
# ============================================================
tracer,meter,instruments=setup_telemetry(
    service_name=settings.app_name,
    environment=settings.environment
)


# ============================================================
# APP STATE
# ============================================================
class AppState:
    is_ready:bool=False
    is_shutting_down:bool=False
    startup_time:float=time.time()
    active_requests:int=0

    @property
    def uptime(self)->float:
        return round(time.perf_counter()-self.startup_time,1)
    
state=AppState()


# ============================================================
# LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Setup logging
    setup_logging(environment=settings.environment,log_level=settings.log_level)

    api_logger.bind(
        version=settings.version,
        environment=settings.environment,
        debug=settings.debug
    ).info(f"🚀 {settings.app_name} starting")

    api_logger.bind(
        openai=    bool(settings.openai_api_key),
        anthropic= bool(settings.anthropic_api_key),
        model=     settings.default_model
    ).info("LLM configuration loaded")

    # Simulate resource initialization
    await asyncio.sleep(0.3)
    state.is_ready = True
    api_logger.info("✅ All resources ready — accepting requests")

    yield

    # Graceful shutdown
    state.is_shutting_down = True
    api_logger.info("🛑 Graceful shutdown initiated")

    timeout, waited = 30.0, 0.0
    while state.active_requests > 0 and waited < timeout:
        api_logger.info(f"Waiting for {state.active_requests} active requests")
        await asyncio.sleep(1.0)
        waited += 1.0

    api_logger.info(f"✅ {settings.app_name} shutdown complete")

# ============================================================
# APP
# ============================================================
app=FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

FastAPIInstrumentor.instrument_app(app)

# ============================================================
# MIDDLEWARE — order matters, last added = first to run
# ============================================================
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_per_minute)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=     ["*"],
    allow_credentials= True,
    allow_methods=     ["*"],
    allow_headers=     ["*"]
)

# ============================================================
# EXCEPTION HANDLERS
# ============================================================

def error_response(status_code, error, message, request_id=None, details=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error":      error,
            "message":    message,
            "details":    details or {},
            "request_id": request_id or str(uuid.uuid4())[:8]
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": " → ".join(str(l) for l in e["loc"]), "issue": e["msg"]}
        for e in exc.errors()
    ]
    return error_response(
        422, "validation_error", "Invalid request data",
        getattr(request.state, "request_id", None),
        {"errors": errors}
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.opt(exception=True).error(f"Unhandled exception: {exc}")
    return error_response(
        500, "internal_server_error", "Something went wrong",
        getattr(request.state, "request_id", None)
    )


# ============================================================
# ROUTERS
# ============================================================

PREFIX = "/api/v1"
app.include_router(auth.router,  prefix=PREFIX)
app.include_router(items.router, prefix=PREFIX)
app.include_router(llm.router,   prefix=PREFIX)


# ============================================================
# HEALTH + METRICS ENDPOINTS
# ============================================================


@app.get("/health", tags=["Health"])
def health():
    return {"status": "alive", "uptime": state.uptime}


@app.get("/ready", tags=["Health"])
def ready():
    if not state.is_ready or state.is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "uptime": state.uptime}
        )
    return {"status": "ready", "uptime": state.uptime}


@app.get("/startup", tags=["Health"])
def startup():
    if not state.is_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "uptime": state.uptime}
        )
    return {"status": "started", "uptime": state.uptime}


@app.get("/metrics", tags=["Health"])
def metrics():
    return {
        "service":     settings.app_name,
        "version":     settings.version,
        "uptime":      state.uptime,
        "environment": settings.environment,
        "note":        "In production: add prometheus-fastapi-instrumentator"
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "app":     settings.app_name,
        "version": settings.version,
        "docs":    "/docs",
        "health":  "/health"
    }