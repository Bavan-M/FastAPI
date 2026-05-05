import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
import time
from fastapi import FastAPI,HTTPException,Request
from typing import Optional
import httpx
import uuid
import random
from contextlib import asynccontextmanager
from pydantic import BaseModel


# ============================================================
# SERVICE REGISTRY — where each service lives
# ============================================================
class ServiceRegistry:
    """Maps service names to their base URLs.
    In production use Kubernetes DNS — services find
    each other by name automatically.
    k8s DNS: http://auth-service.default.svc.cluster.local:8001
    Local:   http://localhost:8001
    """
    SERVICES={
        "auth":os.getenv("AUTH_SERVICE_URL","http://localhost:8001"),
        "llm":os.getenv("LLM_SERVICE_URL",       "http://localhost:8002"),
        "ingestion":os.getenv("INGESTION_SERVICE_URL",       "http://localhost:8003"),
        "retireval":os.getenv("RETRIEVAL_SERVICE_URL", "http://localhost:8004"),
    }

    @classmethod
    def url(cls,service:str,path:str="")->str:
        base=cls.SERVICES.get(service)
        if not base:
            raise ValueError(f"Unknown Service :{service}")
        return f"{base}{path}"
    

# ============================================================
# SERVICE CLIENT — reusable HTTP client with resilience
# ============================================================
class ServiceClient:
    """
    HTTP client for calling other microservices.
    Includes: retry, timeout, circuit breaker, tracing headers.
    Every inter-service call should go through this.
    """
    def __init__(self,service_name:str,timeout:float=10.0,max_retries:int=3,base_delay:float=0.5):
        self.service_name=service_name
        self.timeout=timeout
        self.max_retries=max_retries
        self.base_delay=base_delay
        self._client:Optional[httpx.AsyncClient]=None

        # Circuit breaker state
        self._failures=0
        self._failure_thres=5
        self._last_failures=0.0
        self._recovery_secs=30.0
        self._state="closed"

    async def start(self):
        self._client=httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,
                read=self.timeout,
                write=10.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20
            )
        )

    async def stop(self):
        if self._client:
            await self._client.aclose()

    def _check_circuit(self)->bool:
        """Returns True if request should proceed"""
        if self._state=="closed":
            return True
        if self._state=="open":
            if time.monotonic()-self._last_failures>=self._recovery_secs:
                self._state="half_open"
                print(f"[CB:{self.service_name}] → HALF_OPEN")
                return True
            return False
        return True
    
    def _on_success(self):
        if self._state=="half_open":
            self._state="closed"
            self._failures=0
            print(f"[CB:{self.service_name}] ✅ → CLOSED")
    
    def _on_failure(self):
        self._failures+=1
        self._last_failures=time.monotonic()
        if self._state=="half_open":
            self._state="open"
            print(f"[CB:{self.service_name}] ❌ → OPEN")
        elif self._failures>=self._failure_thres:
            self._state="open"
            print(f"[CB:{self.service_name}] ❌ {self._failures} failures → OPEN")

    async def request(self,method:str,path:str,request_id:str=None,auth_token:str=None,json:dict=None,params:dict=None,raise_on_4xx:bool=True)->dict:
        """
        Make an inter-service HTTP request with full resilience.

        Automatically adds:
        - X-Request-ID for distributed tracing
        - Authorization header for inter-service auth
        - Retry with exponential backoff
        - Circuit breaker protection
        """
        if not self._check_circuit():
            raise HTTPException(
                status_code=503,
                detail={
                    "error":"circuit_open",
                    "service":self.service_name,
                    "message":f"{self.service_name} service temporarily unavaliable"
                }
            )
        url=ServiceRegistry.url(service=self.service_name,path=path)
        headers={
            "X-Request-ID":request_id or str(uuid.uuid4())[:8],
            "X-Source-Service":"api-gateway",
            "Content-type":"application/json"
        }
        if auth_token:
            headers["Authorization"]=f"Bearer {auth_token}"
        last_exc=None
        for attempt in range(1,self.max_retries+1):
            try:
                print(f"[{self.service_name}] {method} {path} attempt {attempt}")
                response=await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params
                )
                if raise_on_4xx and 400<=response.status_code<500:
                    raise HTTPException(status_code=response.status_code,detail=response.json().get("detail",response.text))
                if response.status_code>=500:
                    raise HTTPException(status_code=response.status_code,detail=f"Server error {response.status_code}")
                self._on_success()
                return response.json()
            except HTTPException:
                raise
            except (httpx.TimeoutException,httpx.ConnectError) as e:
                last_exc=e
                self._on_failure()
                print(f"[{self.service_name}] Network error attempt {attempt}: {e}")
            except httpx.HTTPStatusError as e:
                last_exc=e
                self._on_failure()
                print(f"[{self.service_name}] HTTP error attempt {attempt}: {e}")
            if attempt<=self.max_retries:
                delay=self.base_delay*(2**(attempt-1))
                delay+=random.uniform(0,delay*0.1)
                print(f"[{self.service_name}] Retrying in {delay:.2f}s")
                await asyncio.sleep(delay=delay)
        raise HTTPException(
            status_code=503,
            detail=f"{self.service_name} service unavailable after {self.max_retries} attempts"
        )
    
    async def get(self,path:str,**kwargs)->dict:
        return await self.request(method="GET",path=path,**kwargs)
    
    async def post(self,path:str,**kwargs)->dict:
        return await self.request(method="POST",path=path,**kwargs)
    
    async def put(self,path:str,**kwargs)->dict:
        return await self.request(method="PUT",path=path,**kwargs)
    
    async def delete(self,path:str,**kwargs)->dict:
        return await self.request(method="DELETE",path=path,**kwargs)
    

# ============================================================
# SIMULATED MICROSERVICES — run them to test communication
# ============================================================

# AUTH SERVICE (runs on port 8001)
auth_app=FastAPI(title="Auth Service")

fake_users={
    "token-alice":{
        "id":1,
        "username":"alice",
        "email":"alice@gmail.com",
        "role":"admin"
    },
    "token-bob":{
        "id":2,
        "username":"bob",
        "email":"bob@gmail.com",
        "role":"user"
    }
}


@auth_app.get("/health")
def auth_health():
    return {
        "service":"auth",
        "status":"OK"
    }

@auth_app.post("/validate")
async def validate_token(request: Request):
    body  = await request.json()
    token = body.get("token", "")
    user  = fake_users.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"valid": True, "user": user}

@auth_app.get("/users/{user_id}")
def get_user(user_id: int):
    user = next((u for u in fake_users.values() if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

    
# LLM SERVICE (runs on port 8002)
llm_app = FastAPI(title="LLM Gateway Service")

class LLMRequest(BaseModel):
    prompt:     str
    model:      str = "gpt-4"
    max_tokens: int = 512
    user_id:    int = None

@llm_app.get("/health")
def llm_health():
    return {"service": "llm-gateway", "status": "ok"}

@llm_app.post("/generate")
async def llm_generate(req: LLMRequest):
    await asyncio.sleep(0.5)   # simulate LLM latency
    return {
        "response":    f"[{req.model}] Response to: {req.prompt[:30]}",
        "model":       req.model,
        "tokens_used": len(req.prompt.split()) * 10,
        "cost_usd":    len(req.prompt.split()) * 10 * 0.00003
    }

@llm_app.get("/models")
def list_models():
    return {
        "models": [
            {"id": "gpt-4",          "context": 8192},
            {"id": "claude-3-opus",  "context": 200000},
            {"id": "gpt-3.5-turbo",  "context": 4096}
        ]
    }


# API GATEWAY (runs on port 8000)
# This is what clients call — proxies to other services
gateway_clients:dict={}

@asynccontextmanager
async def gateway_lifespan(app:FastAPI):
    for name in ["auth","llm"]:
        client=ServiceClient(service_name=name,timeout=15.0)
        await client.start()
        gateway_clients[name]=client
    print("✅ API Gateway ready — service clients initialized")
    yield
    for client in gateway_clients.values():
        await client.stop()
    print("✅ API Gateway shutdown — connections closed")

gateway_app=FastAPI(title="API Gateway",lifespan=gateway_lifespan)

@gateway_app.get("/health")
async def gateway_health():
    """
    Aggregate health from all services.
    Returns overall status and per-service status.
    """
    health={"gateway":"ok","services":{}}
    for service_name,client in gateway_clients.items():
        try:
            result=await client.get("/health")
            health["services"][service_name]=result.get("status","ok")
        except Exception as e:
            health["services"][service_name]=f"error:{e}"
    all_ok=all(v=="ok" for v in health["services"].values())
    health["overall"]="healthy" if all_ok else "degraded"
    return health



@gateway_app.post("/api/generate")
async def gateway_generate(req:LLMRequest,request:Request):
    """
    Gateway route:
    1. Validate user token with Auth Service
    2. Call LLM Service with validated user context
    3. Return response

    Client only talks to gateway — never directly to services.
    """
    request_id=request.headers.get("X-Request-ID",str(uuid.uuid4())[:8])
    token=request.headers.get("Authorization","").replace("Bearer ","")

    # Step 1 — Validate with Auth Service
    try:
        auth_result=await gateway_clients["auth"].post(
            "/validate",
            json={"token":token},
            request_id=request_id
        )
        user=auth_result["user"]
    except HTTPException as e:
        if e.status_code==401:
            raise HTTPException(status_code=401, detail="Invalid token")
        raise


    # Step 2 — Call LLM Service
    req.user_id=user["id"]
    llm_result=await gateway_clients["llm"].post(
        "/generate",
        json=req.dict(),
        request_id=request_id
    )
    return {
        **llm_result,
        "requested_by":user["username"],
        "request_id":request_id
    }

@gateway_app.get("/api/models")
async def gateway_models():
    """Proxy to LLM service — no auth needed for public info"""
    return await gateway_clients["llm"].get("/models")

# ============================================================
# RUN INSTRUCTIONS
# ============================================================

INSTRUCTIONS = """
To test service communication — run these in separate terminals:

Terminal 1 — Auth Service:
  uvicorn phase8.day1.02_service_communication:auth_app --port 8001 --reload

Terminal 2 — LLM Service:
  uvicorn phase8.day1.02_service_communication:llm_app --port 8002 --reload

Terminal 3 — API Gateway:
  uvicorn phase8.day1.02_service_communication:gateway_app --port 8000 --reload

Then test:
  # Health — aggregates all services
  curl http://localhost:8000/health

  # Generate — goes through auth + llm
  curl -X POST http://localhost:8000/api/generate \\
    -H "Authorization: Bearer token-alice" \\
    -H "Content-Type: application/json" \\
    -d '{"prompt": "What is LangGraph?"}'

  # Models — proxied to LLM service
  curl http://localhost:8000/api/models

Try stopping auth service — see circuit breaker in action.
"""
print(INSTRUCTIONS)
