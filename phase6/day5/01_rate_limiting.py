import sys,os
sys.path.insert(0,os.path.dirname(__file__))
from collections import deque,defaultdict
import asyncio
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI,Request,HTTPException,Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel


# ============================================================
# RATE LIMIT TIERS — different limits per user plan
# ============================================================
RATE_LIMMIT_TIERS={
    "free":{
        "requests_per_minute":10,
        "requests_per_day":100,
        "llm_calls_per_minute":3,
        "llm_calls_per_day":20
    },
    "pro": {
        "requests_per_minute": 60,
        "requests_per_day":    10_000,
        "llm_calls_per_minute": 20,
        "llm_calls_per_day":   500,
    },
    "enterprise": {
        "requests_per_minute": 600,
        "requests_per_day":    1_000_000,
        "llm_calls_per_minute": 200,
        "llm_calls_per_day":   10_000,
    }
}

# ============================================================
# SLIDING WINDOW RATE LIMITER
# ============================================================
class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter.
    Tracks timestamps of recent requests per client.
    More accurate than fixed window — no boundary burst problem.
    """
    def __init__(self):
        self._windows:dict[str,deque]=defaultdict(deque)
        self._lock=asyncio.Lock()

    async def is_allowed(self,key:str,limit:int,window_secs:int=60)->tuple[bool,dict]:
        """
        Returns (is_allowed, metadata).
        metadata contains rate limit headers info.
        """
        async with self._lock:
            now=time.monotonic()
            window=self._windows[key]

            # Remove timestamps outside the window
            cutoff=now-window_secs
            while window and window[0]<=cutoff:
                window.popleft()
            
            current_count=len(window)
            remaining=max(0,limit-current_count)
            reset_at=int(time.time())+window_secs

            if current_count>=limit:
                return False,{
                    "limit":limit,
                    "remaining":0,
                    "reset":reset_at,
                    "retry_after":window_secs-(now-window[0]) if window else window_secs
                }
            
            # Allow — record this request
            window.append(now)
            return True,{
                "limit":limit,
                "remaining":remaining-1,
                "reset":reset_at,
                "retry_after":0
            }
    def get_stats(self)->dict:
        return {
            "tracked_clients":len(self._windows),
            "clients":{k:len(v) for k,v in self._windows.items()}
        }

# ============================================================
# TOKEN BUCKET LIMITER — allows short bursts
# ============================================================
class TokenBucketLimiter:
    """
    Token bucket algorithm.
    Each client has a bucket of tokens.
    Tokens refill at a constant rate.
    Allows short bursts (up to bucket size) then throttles.

    Good for: LLM endpoints where you want to allow
    occasional bursts but smooth sustained traffic.
    """
    def __init__(self,rate:float,burst:int):
        """
        rate:  tokens added per second
        burst: maximum tokens (bucket size)
        """
        self.rate=rate
        self.burst=burst

        # client_key → (tokens, last_refill_time)
        self._buckets:dict[str,list]={}
        self._lock=asyncio.Lock()

    async def consume(self,key:str,tokens:int=1)->bool:
        async with self._lock:
            now=time.monotonic()

            if key not in self._buckets:
                self._buckets[key]=[float(self.burst),now]
            
            bucket_tokens,last_refill=self._buckets[key]

            # Refill tokens based on elapsed time
            elapsed=now-last_refill
            new_tokens=elapsed*self.rate
            bucket_tokens=min(self.burst,bucket_tokens+new_tokens)

            if bucket_tokens<tokens:
                self._buckets[key]=[bucket_tokens,now]
                return False
            
            # Consume tokens
            self._buckets[key]=[bucket_tokens-tokens,now]
            return True
        
    
# ============================================================
# RATE LIMIT MIDDLEWARE FOR ALL THE ENDPOINTS 
# ============================================================
# Global limiters
ip_limiter=SlidingWindowRateLimiter()
user_limiter=SlidingWindowRateLimiter()
llm_limiter=TokenBucketLimiter(rate=1.0,burst=10) # # 1 LLM call/sec, burst 10

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware.
    Applied to ALL requests before they reach routes.
    """
    # Endpoints that bypass rate limiting
    EXEMPT_PATHS={"/health","/ready","/metrics","/docs","/openapi.json"}

    async def dispatch(self, request:Request, call_next):
        # Skip exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        
        # Get client identifier
        # In production: extract from JWT token
        # For demo: use IP address
        client_ip=request.headers.get("X-Forwarded-For","").split(",")[0].strip()
        client_ip=client_ip or (request.client.host if request.client else "unknown")

        # Apply IP-based rate limit (60 req/min for all IPs)
        allowed,meta=await ip_limiter.is_allowed(key=f"ip:{client_ip}",limit=60,window_secs=60)

        if not allowed:
            return  JSONResponse(
                status_code=429,
                content={
                    "error":"rate_limit_exceeded",
                    "message":"Too many requests.Please slow down",
                    "retry_after":meta["retry_after"]
                },
                headers={
                    "X-RateLimit-Limit":     str(meta["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset":     str(meta["reset"]),
                    "Retry-After":           str(int(meta["retry_after"]))
                }
            )
        # Process request
        response=await call_next(request)

        # Add rate limit headers to EVERY response
        # Clients use these to self-throttle before hitting 429
        response.headers["X-RateLimit-Limit"]=str(meta["limit"])
        response.headers["X-RateLimit-Remaining"]=str(meta["remaining"])
        response.headers["X-RateLimit-Reset"]=str(meta["reset"])

        return response
    

# ============================================================
# PER-ENDPOINT RATE LIMIT DEPENDENCY FOR LLM CALLS FOR PARTICULAR USER
# ============================================================
def rate_limit_dependency(calls_per_minute:int=60,tier:str=None):
    """
    FastAPI dependency for per-endpoint rate limiting.
    More granular than middleware — different limits per route.

    Usage:
        @app.post("/llm/generate")
        async def generate(
            _: None = Depends(rate_limit_dependency(calls_per_minute=10))
        ):
    """
    async def check_rate_limit(request:Request):
        client_ip=request.client.host if request.client else "unknown"
        endpoint=request.url.path.replace("/","_")
        key=f"endpoint:{endpoint}:{client_ip}"
        limit=calls_per_minute
        if tier and tier in RATE_LIMMIT_TIERS:
            limit=RATE_LIMMIT_TIERS[tier]["llm_calls_per_minute"]
        allowed,meta=await user_limiter.is_allowed(key=key,limit=limit,window_secs=60)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error":"rate_limit_exceeded",
                    "endpoint":request.url.path,
                    "limit":meta["limit"],
                    "retry_after":meta["retry_after"]
                },
                headers={
                    "Retry-After":           str(int(meta["retry_after"])),
                    "X-RateLimit-Limit":     str(meta["limit"]),
                    "X-RateLimit-Remaining": "0"
                }
            )
        
        return meta
    return check_rate_limit


@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ Rate limiting ready")
    yield

app=FastAPI(title="Rate Limiting Demo",lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)

class GenerateRequest(BaseModel):
    prompt:str
    tier:str="free"

@app.post("/llm/generate")
async def generate_llm(req:GenerateRequest,_meta:dict=Depends(rate_limit_dependency(calls_per_minute=60))):
    """
    Stricter rate limit — 10 LLM calls per minute.
    LLM calls are expensive so we limit them more aggressively.
    """
    # Token bucket check for LLM calls
    client_id=f"user:{req.tier}"
    allowed=await llm_limiter.consume(key=client_id,tokens=1)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="LLM rate limit exceeded.Token bucket empty"
        )
    await asyncio.sleep(0.5)
    return {
        "response":   f"Response to: {req.prompt[:30]}",
        "tier":       req.tier,
        "tip":        "Check response headers for rate limit info"
    }

@app.get("/rate-limit/stats")
async def rate_limit_stats():
    return {
        "ip_limiter":   ip_limiter.get_stats(),
        "user_limiter": user_limiter.get_stats()
    }


@app.get("/health")
def health():
    return {"status": "ok"}
