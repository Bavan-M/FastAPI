import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


# ============================================================
# SCHEMAS — evolve between versions
# ============================================================

# V1 schemas — original
class UserV1(BaseModel):
    id:       int
    username: str
    email:    str

class GenerateRequestV1(BaseModel):
    prompt: str
    model:  str = "gpt-4"

class GenerateResponseV1(BaseModel):
    response: str
    model:    str


# V2 schemas — improved
class UserV2(BaseModel):
    id:           int
    username:     str
    email:        str
    display_name: str              # new field
    created_at:   datetime         # new field
    preferences:  dict = {}        # new field

class GenerateRequestV2(BaseModel):
    prompt:       str
    model:        str = "gpt-4"
    max_tokens:   int = 512        # new field
    temperature:  float = 0.7      # new field
    stream:       bool = False     # new field
    system_prompt: Optional[str] = None  # new field

class GenerateResponseV2(BaseModel):
    response:     str
    model:        str
    tokens_used:  int              # new field
    latency_ms:   float            # new field
    request_id:   str              # new field


# ============================================================
# V1 ROUTER — original API
# ============================================================

router_v1 = APIRouter(prefix="/v1", tags=["V1"])


@router_v1.get("/users/{user_id}", response_model=UserV1)
def get_user_v1(user_id: int):
    """V1 — simple user response"""
    return {"id": user_id, "username": "alice", "email": "alice@test.com"}


@router_v1.post("/generate", response_model=GenerateResponseV1)
async def generate_v1(req: GenerateRequestV1):
    """V1 — basic generation, no streaming, no token count"""
    import asyncio
    await asyncio.sleep(0.1)
    return {
        "response": f"V1 response to: {req.prompt[:30]}",
        "model":    req.model
    }


@router_v1.get("/models")
def list_models_v1():
    """V1 — simple model list"""
    return {"models": ["gpt-4", "gpt-3.5-turbo"]}


# ============================================================
# V2 ROUTER — improved API
# ============================================================

router_v2 = APIRouter(prefix="/v2", tags=["V2"])


@router_v2.get("/users/{user_id}", response_model=UserV2)
def get_user_v2(user_id: int):
    """V2 — richer user response with new fields"""
    return {
        "id":           user_id,
        "username":     "alice",
        "email":        "alice@test.com",
        "display_name": "Alice Smith",       # new in v2
        "created_at":   datetime.utcnow(),   # new in v2
        "preferences":  {"theme": "dark"}    # new in v2
    }


@router_v2.post("/generate", response_model=GenerateResponseV2)
async def generate_v2(req: GenerateRequestV2, request: Request):
    """V2 — richer response with tokens, latency, request_id"""
    import asyncio, time, uuid
    start = time.perf_counter()
    await asyncio.sleep(0.1)
    latency = (time.perf_counter() - start) * 1000

    return {
        "response":    f"V2 response to: {req.prompt[:30]}",
        "model":       req.model,
        "tokens_used": len(req.prompt.split()) * 10,  # new in v2
        "latency_ms":  round(latency, 2),              # new in v2
        "request_id":  str(uuid.uuid4())[:8]           # new in v2
    }


@router_v2.get("/models")
def list_models_v2():
    """V2 — richer model info"""
    return {
        "models": [
            {"id": "gpt-4",          "context_window": 8192,  "supports_streaming": True},
            {"id": "gpt-3.5-turbo",  "context_window": 4096,  "supports_streaming": True},
            {"id": "claude-3-opus",  "context_window": 200000, "supports_streaming": True},
        ]
    }


# ============================================================
# DEPRECATION MIDDLEWARE
# ============================================================
class DeprecationMiddleware:
    """
    Adds deprecation warning headers to v1 responses.
    Clients see the warning and know to migrate.
    Standard way to sunset old API versions.
    """
    def __init__(self,app):
        self.app=app

    async def __call__(self, scope,recieve,send):
        if scope["type"]=="http":
            path=scope.get("path","")

            async def send_with_depreciation(message):
                if message["type"] == "http.response.start" and "/v1/" in path:
                    # Add deprecation headers to all V1 responses
                    headers = dict(message.get("headers", []))
                    headers[b"deprecation"]  = b"true"
                    headers[b"sunset"]       = b"2027-01-01"
                    headers[b"link"]         = b'</api/v2>; rel="successor-version"'
                    headers[b"warning"]      = b'299 - "This API version is deprecated. Migrate to /v2"'
                    message = {**message, "headers": list(headers.items())}
                await send(message)

            await self.app(scope,recieve,send_with_depreciation)
        else:
            await self.app(scope,recieve,send)


# ============================================================
# HEADER-BASED VERSIONING — alternative approach
# ============================================================

router_header = APIRouter(tags=["Header Versioning"])


@router_header.get("/users/{user_id}")
def get_user_header_version(
    user_id:       int,
    api_version:   str = Header(default="1", alias="X-API-Version")
):
    """
    Single endpoint that handles multiple versions via header.
    Client sends: X-API-Version: 2
    Cleaner URLs but less obvious versioning.
    """
    if api_version == "2":
        return {
            "id":           user_id,
            "username":     "alice",
            "email":        "alice@test.com",
            "display_name": "Alice Smith",
            "version":      "2"
        }
    else:
        return {
            "id":       user_id,
            "username": "alice",
            "email":    "alice@test.com",
            "version":  "1"
        }


# ============================================================
# VERSION INFO ENDPOINT
# ============================================================

@router_v1.get("/version")
@router_v2.get("/version")
def version_info(request: Request):
    """Each version reports its own info and deprecation status"""
    path    = request.url.path
    version = "v1" if "/v1/" in path else "v2"

    info = {
        "v1": {
            "version":      "1.0.0",
            "status":       "deprecated",
            "sunset_date":  "2027-01-01",
            "migrate_to":   "/api/v2",
            "docs":         "/docs#tag/V1"
        },
        "v2": {
            "version":      "2.0.0",
            "status":       "stable",
            "released":     "2026-01-01",
            "docs":         "/docs#tag/V2"
        }
    }
    return info[version]


# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(
    title="Versioned Gen AI API",
    version="2.0.0",
    description="""
    ## API Versioning Demo

    - **V1** `/api/v1/` — deprecated, sunset 2027-01-01
    - **V2** `/api/v2/` — current stable version

    Migrate from V1 to V2 to access new features.
    """
)

app.add_middleware(DeprecationMiddleware)

# Mount both versions under /api prefix
app.include_router(router_v1, prefix="/api")
app.include_router(router_v2, prefix="/api")
app.include_router(router_header, prefix="/api/header")


@app.get("/")
def root():
    return {
        "api":      "Versioned Gen AI API",
        "versions": {
            "v1": {"url": "/api/v1", "status": "deprecated"},
            "v2": {"url": "/api/v2", "status": "stable"}
        },
        "docs": "/docs"
    }
