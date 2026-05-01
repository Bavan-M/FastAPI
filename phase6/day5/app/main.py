import os
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes import router


# ============================================================
# STATE
# ============================================================

class AppState:
    is_ready:        bool  = False
    is_shutting_down: bool = False
    startup_time:    float = time.time()
    active_requests: int   = 0

    @property
    def uptime(self) -> float:
        return round(time.time() - self.startup_time, 1)


state = AppState()


# ============================================================
# MIDDLEWARE
# ============================================================

class RequestTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if state.is_shutting_down and request.url.path not in ("/health", "/ready"):
            return JSONResponse(
                status_code=503,
                content={"error": "shutting_down"},
                headers={"Retry-After": "5"}
            )
        state.active_requests += 1
        try:
            return await call_next(request)
        finally:
            state.active_requests -= 1


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n🚀 Starting {os.getenv('APP_NAME', 'Gen AI API')}")
    print(f"   ENV:     {os.getenv('ENV', 'production')}")
    print(f"   VERSION: {os.getenv('VERSION', '1.0.0')}")
    await asyncio.sleep(0.5)   # simulate initialization
    state.is_ready = True
    print("✅ Ready!\n")
    yield
    state.is_shutting_down = True
    print("\n🛑 Shutting down...")
    timeout, waited = 30.0, 0.0
    while state.active_requests > 0 and waited < timeout:
        await asyncio.sleep(1.0)
        waited += 1.0
    print("✅ Shutdown complete\n")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=   os.getenv("APP_NAME", "Gen AI API"),
    version= os.getenv("VERSION", "1.0.0"),
    lifespan=lifespan
)

app.add_middleware(RequestTrackingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=  os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=  ["*"],
    allow_headers=  ["*"],
    allow_credentials=True
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "alive", "uptime": state.uptime}


@app.get("/ready")
async def ready():
    if not state.is_ready or state.is_shutting_down:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready", "uptime": state.uptime}