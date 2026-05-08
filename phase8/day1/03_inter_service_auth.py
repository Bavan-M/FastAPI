import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from enum import Enum
from jose import jwt,JWTError
import time
import uuid
from fastapi import HTTPException,Depends,FastAPI,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import asyncio

# ============================================================
# SERVICE IDENTITY CONFIGURATION
# ============================================================

# Shared secret — all services know this
# In production: store in AWS Secrets Manager / Kubernetes Secrets
SERVICE_JWT_SECRET="shared-service-secret-32-chars-min"
SERVICE_JWT_ALGORITHM="HS256"
SERVICE_TOKEN_TTL=300

class ServiceName(str,Enum):
    """
    All known services in the system.
    Used as the 'sub' claim in service tokens.
    """
    API_GATEWAY="api-gateway"
    AUTH_SERVICE="auth-service"
    LLM_GATEWAY="llm-gateway"
    INGESTION="ingestion-service"
    RETRIEVAL="retrieval-service"
    AGENT="agent-service"
    NOTIFICATION="notification-service"


# Service permissions — what each service is allowed to call
SERVICE_PERMISSIONS={
    ServiceName.API_GATEWAY:[
        "auth-service:validate",
        "auth-service:users:read",
        "llm-gateway:generate",
        "llm-gateway:models:read",
        "ingestion-service :documents:write"
        "retrieval-service:search"
    ],
    ServiceName.AGENT: [
        "llm-gateway:generate",
        "retrieval:search",
        "ingestion:documents:read",
    ],
    ServiceName.INGESTION: [
        "llm-gateway:embed",
        "retrieval:store",
        "notification:send",
    ],
    ServiceName.RETRIEVAL: [
        "llm-gateway:embed",
    ]
}


# ============================================================
# SERVICE TOKEN CREATION + VALIDATION
# ============================================================
def create_service_token(caller_service:ServiceName,target_service:ServiceName,permissions:list=None)->str:
    """
    Create a JWT for service-to-service authentication.
    Short-lived (5 min) — services request tokens per call or cache briefly.

    The 'aud' (audience) claim specifies the target service.
    Target service rejects tokens intended for other services.
    """
    return jwt.encode(
        {
            "sub":caller_service,
            "aud":target_service,
            "iat":int(time.time()),
            "exp":int(time.time())+SERVICE_TOKEN_TTL,
            "jti":str(uuid.uuid4()),
            "permissions":permissions or SERVICE_PERMISSIONS.get(caller_service,[]),
            "type":"service"
        },
        key=SERVICE_JWT_SECRET,
        algorithm=SERVICE_JWT_ALGORITHM
    )


def validate_service_token(token:str,expected_caller_serice:ServiceName=None,expected_target_service:str=None,required_permission:str=None)->dict:
    """
    Validate a service JWT.
    Checks: signature, expiry, audience, optionally permission.
    """
    try:
        payload=jwt.decode(
            token=token,
            key=SERVICE_JWT_SECRET,
            algorithms=[SERVICE_JWT_ALGORITHM],
            options={"verify_aud":False}
        )
    except JWTError as e:
        raise HTTPException(status_code=401,detail=f"Invalid service token : {e}")
    
    # Must be a service token not a user token
    if payload.get("type")!="service":
        raise HTTPException(status_code=401,detail="Not a service token")
    
    # Verify caller if specified
    if expected_caller_serice and payload.get("sub")!=expected_caller_serice:
        raise HTTPException(status_code=403,detail=f"Expected caller {expected_caller_serice}, got {payload.get('sub')}")
    
    # Verify caller if specified
    if expected_target_service and payload.get("aud")!=expected_target_service:
        raise HTTPException(status_code=403,detail=f"Expected target {expected_target_service}, got {payload.get('aud')}")
    
    # Check permission if specified
    if required_permission:
        permissions=payload.get("permisiions",[])
        if required_permission not in permissions:
            raise HTTPException(status_code=403,detail=f"Service {payload.get('sub')} lacks permission: {required_permission}")
        
    return payload


# ============================================================
# SERVICE AUTH MIDDLEWARE
# ============================================================

# Extracts the Authorization: Bearer <token> header from incoming HTTP requests.
# auto_error=False means: Don't automatically raise 401 errors. Let us handle missing tokens with custom error messages.
security=HTTPBearer(auto_error=False)

class ServiceAuthContext(BaseModel):
    caller_service:str
    permissions:list
    token_id:str

async def require_service_auth(credentials:Optional[HTTPAuthorizationCredentials]=Depends(security),required_permissions:str=None)->ServiceAuthContext:
    """
    FastAPI dependency for service-to-service auth.
    Use this on endpoints that should only be called by other services.
    """
    if not credentials:
        raise HTTPException(status_code=401,detail="Service token required — this endpoint is for internal use only")
    
    payload=validate_service_token(credentials.credentials,required_permission=required_permissions)

    return ServiceAuthContext(
        caller_service=payload.get("sub"),
        permissions=payload.get("permissions",[]),
        token_id=payload.get("jti","")
    )

def require_permission(permission:str):
    """
    Dependency factory — require a specific permission.

    Usage:
        @app.post("/generate")
        async def generate(
            _: ServiceAuthContext = Depends(require_permission("llm-gateway:generate"))
        ):
    """
    async def check(credentials:Optional[HTTPAuthorizationCredentials]=Depends(security))->ServiceAuthContext:
        if not credentials:
            raise HTTPException(status_code=401,detail="Service token required")
        
        payload=validate_service_token(credentials.credentials,required_permission=permission)

        return ServiceAuthContext(
            caller_service=payload["sub"],
            permissions=payload.get("permissions",[]),
            token_id=payload.get("jti","")
        )
    return check #Returns Function object it executes when When FastAPI calls it later



# ============================================================
# TOKEN CACHE — avoid creating tokens on every request
# ============================================================

class ServiceTokenCache:
    """
    Cache service tokens to avoid JWTencode overhead on every request.
    Tokens are valid for 5 min — refresh 30s before expiry.
    """
    def __init__(self):
        self._cache:dict={} # (caller, target) → (token, expires_at)

    def get(self,caller:ServiceName,target:ServiceName)->Optional[str]:
        key=(caller,target)
        item=self._cache.get(key)
        if not item:
            return None
        token,expires_in=item

        # Refresh 30s before expiry
        if time.time()>=expires_in-30:
            return None
        return token
    
    def set(self,caller:ServiceName,target:ServiceName,token:str):
        key=(caller,target)
        self._cache[key]=(token,time.time()+SERVICE_TOKEN_TTL)

    def get_or_create(self,caller:ServiceName,target:ServiceName)->str:
        token=self.get(caller,target)
        if not token:
            token=create_service_token(caller_service=caller,target_service=target)
            self.set(caller,target,token)
            print(f"[TOKEN CACHE] Created token: {caller} → {target}")
        return token
    

token_cache=ServiceTokenCache()

@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ LLM Gateway with service auth ready")
    yield

app=FastAPI(title="LLM Gateway — Inter-service Auth Demo",lifespan=lifespan)

class GenerateRequest(BaseModel):
    prompt:     str
    model:      str = "gpt-4"
    max_tokens: int = 512


@app.post("/generate")
async def generate(req:GenerateRequest,request:Request,ctx:ServiceAuthContext=Depends(require_permission("llm-gateway:generate"))):
    """
    Only callable by services with 'llm-gateway:generate' permission.
    Direct calls without service token → 401.
    """
    print(f"[LLM] Called by service: {ctx.caller_service}")
    await asyncio.sleep(0.3)

    return {
        "response":     f"[{req.model}] Response to: {req.prompt[:30]}",
        "model":        req.model,
        "tokens_used":  len(req.prompt.split()) * 10,
        "called_by":    ctx.caller_service,
        "request_id":   request.headers.get("X-Request-ID", "")
    }

@app.post("/embed")
async def embed(
    text: str,
    ctx:  ServiceAuthContext = Depends(
        require_permission("llm-gateway:embed")
    )
):
    """Only ingestion and retrieval services can call /embed"""
    await asyncio.sleep(0.1)
    return {
        "embedding":  [0.1, 0.2, 0.3, 0.4, 0.5],
        "called_by":  ctx.caller_service
    }


@app.get("/models")
async def list_models():
    """Public endpoint — no service auth needed"""
    return {"models": ["gpt-4", "claude-3", "gpt-3.5-turbo"]}


@app.get("/health")
def health():
    return {"service": "llm-gateway", "status": "ok"}


# ============================================================
# DEMO — TEST INTER-SERVICE AUTH
# ============================================================

@app.get("/demo/token-flow")
async def demo_token_flow():
    """
    Demonstrates the complete inter-service auth flow.
    Shows how API Gateway gets a token and calls LLM Gateway.
    """
    results = {}

    # API Gateway creates service token for LLM Gateway
    token = token_cache.get_or_create(
        ServiceName.API_GATEWAY,
        ServiceName.LLM_GATEWAY
    )
    results["token_created"] = token[:30] + "..."

    # Validate the token
    payload = validate_service_token(token)
    results["token_payload"] = {
        "caller":      payload["sub"],
        "target":      payload["aud"],
        "permissions": payload["permissions"][:3],
        "expires_in":  payload["exp"] - int(time.time())
    }

    # Show what happens with wrong permission
    try:
        agent_token = create_service_token(
            ServiceName.NOTIFICATION,   # notification service
            ServiceName.LLM_GATEWAY
        )
        validate_service_token(
            agent_token,
            required_permission="llm-gateway:generate"
        )
        results["permission_check"] = "passed (unexpected)"
    except HTTPException as e:
        results["permission_check"] = f"correctly blocked: {e.detail}"

    return results





