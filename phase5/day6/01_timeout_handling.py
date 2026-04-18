import os,sys
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
from fastapi import FastAPI,HTTPException,Request
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager


# ============================================================
# TIMEOUT LEVELS — different ops need different deadlines
# ============================================================
class TimeoutConfig:
    """Cnetralized timeout config
    Tune these based on your actual SLA's
    """
    DB_QUERY=3.0
    EMBEDDING_CALL=10.0
    LLM_GENERATION=45.0
    VECTOR_SEARCH=5.0
    HEALTH_CHECK=2.0
    FILE_PROCESSING=120.0
    HTTP_CONNECT=5.0
    HTTP_READ=30.0


# ============================================================
# SIMULATED EXTERNAL SERVICES
# ============================================================
async def simulate_llm_call(prompt:str,artificial_delay:float=3.0)->str:
    """Simulates an LLM API call that sometimes takes too long"""
    await asyncio.sleep(delay=artificial_delay)
    return f"LLM response to {prompt}"

async def simulate_embedding(text:str,artificial_delay:float=0.5)->list:
    """Simulates an embedding API call"""
    await asyncio.sleep(delay=artificial_delay)
    return [0.1, 0.2, 0.3, 0.4, 0.5]

async def simulate_db_query(query: str, artificial_delay: float = 0.1) -> list:
    """Simulates a database query"""
    await asyncio.sleep(artificial_delay)
    return [{"id": 1, "content": f"Result for {query}"}]


# ============================================================
# PATTERN 3 — Global request timeout
# Middleware that kills any request taking too long
# ============================================================

class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Hard limit on total request duration.
    Protects server from any single request hanging forever."""
    def __init__(self, app, timeout:float=60.0):
        super().__init__(app)
        self.timeout=timeout
    
    async def dispatch(self, request:Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                content={
                    "error":"request_timeout",
                    "message":f"Request exceeded maximum allowed time of {self.timeout}s",
                    "path":str(request.url)
                }
            )



@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ Timeout handling demo ready")
    yield


app=FastAPI(title="Timeout Handling",lifespan=lifespan)
app.add_middleware(RequestTimeoutMiddleware,timeout=30.0)

# ============================================================
# PATTERN 1 — asyncio.wait_for (simplest)
# ============================================================
async def with_timeout(coro,timeout:float,operation_name:str="operation"):
    """Wrap any coroutine with a timeout.
    Raises TimeoutError if not completed in time.
    """
    try:
        return await asyncio.wait_for(coro,timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504,
                            detail=f"{operation_name} time out after {timeout}s")
    
@app.get("/timeout/basic")
async def basic_timeout(delay:float=2.0,timeout:float=3.0):
    """
    Shows basic timeout pattern.
    Try: delay=2 timeout=3 → success
    Try: delay=5 timeout=3 → timeout error
    """
    start=time.perf_counter()

    try:
        result=await with_timeout(
            coro=simulate_llm_call(prompt="what is RAG",artificial_delay=delay),
            timeout=timeout,
            operation_name="LLM generation"
        )
        duration=time.perf_counter()-start
        return {"result":result,"duration_ms":round(duration*1000)}
    except HTTPException:
        duration=time.perf_counter()-start
        raise

# ============================================================
# PATTERN 2 — Per-operation timeout config
# ============================================================
@app.post("/generate")
async def generate_with_timeout(prompt:str):
    """
    Each operation gets its own timeout budget.
    Total request timeout = sum of all operation timeouts.
    """
    start=time.perf_counter()
    results={}

    # Step 1 — Embed query (fast — 10s timeout)
    try:
        embedding=await with_timeout( # since it is await it stops here until 0.3 is complete
            coro=simulate_embedding(text=prompt,artificial_delay=0.3),
            timeout=TimeoutConfig.EMBEDDING_CALL,
            operation_name="Embedding"
        )
        results["embedding"]=f"{len(embedding)} dims"
    except HTTPException as e:
        results["embedding_error"]=e.detail
    
    # Step 2 — Vector search (medium — 5s timeout)
    try:
        chunks = await with_timeout(
            simulate_db_query(prompt, artificial_delay=0.2),
            timeout=TimeoutConfig.VECTOR_SEARCH,
            operation_name="Vector search"
        )
        results["chunks_found"] = len(chunks)
    except HTTPException as e:
        results["search_error"] = e.detail

    # Step 3 — LLM generation (slow — 45s timeout)
    try:
        response = await with_timeout(
            simulate_llm_call(prompt, artificial_delay=1.0),
            timeout=TimeoutConfig.LLM_GENERATION,
            operation_name="LLM generation"
        )
        results["response"] = response
    except HTTPException as e:
        results["llm_error"] = e.detail
        results["response"] = "Sorry, generation timed out. Please try again."

    duration=time.perf_counter()-start
    return {**results,"total_ms":round(duration*1000)}


# ============================================================
# PATTERN 4 — Deadline propagation
# Pass remaining time budget through call chain
# ============================================================

class DeadLineContext:
    """
    Tracks remaining time budget across multiple operations.
    Prevents total request time from exceeding a limit
    even when each individual operation is within its own timeout.
    """
    def __init__(self,total_budget:float):
        self.deadline=time.monotonic()+total_budget
        self.operations=[]

    @property
    def remaining(self)->float:
        return max(0,self.deadline-time.monotonic())
    
    @property
    def is_expired(self)->bool:
        return time.monotonic()>=self.deadline
    
    async def run(self,coro,operation_name:str):
        if self.is_expired:
            raise HTTPException(
                status_code=504,
                detail=f"Request deadline exceeded before {operation_name}"
            )
        operation_timeout=min(self.remaining,30.0)
        start=time.monotonic()
        try:
            result=await asyncio.wait_for(
                coro,
                timeout=operation_timeout
            )
            elapsed=time.monotonic()-start
            self.operations.append({
                "name":operation_name,
                "duration_ms":round(elapsed*1000)
            })
            return result
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail=f"{operation_name} timed out. Budget exhausted."
            )
        
@app.post("/generate/deadline")
async def generate_with_deadline(prompt:str,total_budget:float=10.0):
    """Total request has a fixed time budget.
    Each step uses from the same budget.
    """
    ctx=DeadLineContext(total_budget=total_budget)

    # All steps share the same budget
    embedding=await ctx.run(coro=simulate_embedding(text=prompt,artificial_delay=3.0),operation_name="embedding")
    chunks=await ctx.run(coro=simulate_db_query(query=prompt,artificial_delay=6.0),operation_name="vector_search")
    response=await ctx.run(coro=simulate_llm_call(prompt=prompt,artificial_delay=1.0),operation_name="llm_generation")
    return{
        "response":response,
        "budget_used_ms":round((total_budget-ctx.remaining)*1000),
        "budget_remaining_ms":round(ctx.remaining*1000),
        "operations":ctx.operations
    }


# ============================================================
# PATTERN 5 — Timeout with fallback
# Don't just fail — return something useful
# ============================================================

@app.post("/generate/with-fallback")
async def generate_with_fallback(prompt:str):
    """If LLM times out → return cached or default response.
    Users get something instead of an error.
    Graceful degradation.
    """
    # Try fast model first (5s timeout)
    try:
        response=await asyncio.wait_for(
            simulate_llm_call(prompt=prompt,artificial_delay=5.0),
            timeout=5.0
        )
        return {"response":response,"source":"llm","degraded":False}
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] Primary LLM timed out — using fallback")
    
    # Fallback 1 — try faster/cheaper model (3s timeout)
    try:
        response=await asyncio.wait_for(
            simulate_llm_call(prompt=prompt,artificial_delay=1.0),
            timeout=3.0
        )
        return {"response":response,"source":"fallback_llm","degraded":True}
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] Fallback LLM also timed out — using cache")

    # Fallback 2 — return cached/default response
    return {
        "response": "I'm experiencing high load. Please try again in a moment.",
        "source": "fallback_message",
        "degraded": True
    }

