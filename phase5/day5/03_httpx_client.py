import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException
from contextlib import asynccontextmanager
import httpx
import time
import asyncio
from typing import Optional
import random
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

http_client:httpx.AsyncClient=None

@asynccontextmanager
async def lifespan(app:FastAPI):
    global http_client
    # Create shared client — connection pool reused across requests
    http_client=httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0, #How long Your server establishes a TCP connection to OpenAI's server (handshake)
            read=30.0, #How long Your server waits for OpenAI to PROCESS and SEND BACK the response
            write=10.0, #How long Your server sends the request data (headers, JSON body) to OpenAI
            pool=5.0 #How long Your server waits to get an available connection from the pool
        ),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20
        ),
        headers={"User-Agent":"MyGenAIApp/1.0"}
    )
    print("✅ HTTP client ready")
    yield
    await http_client.aclose()
    print("✅ HTTP client closed")

app=FastAPI(title="httpx Client Demo",lifespan=lifespan)


@app.get("/http/basic")
async def basic_requests():
    """GET, POST, headers, params"""
    # GET request
    response=await http_client.get(url="https://httpbin.org/get",params={"foo":"bar","baz":"qux"})
    response.raise_for_status()
    get_data=response.json()

    # POST with JSON body
    post_response=await http_client.post(
        url="https://httpbin.org/post",
        json={"prompt":"Hello","model":"htp-3.5-turbo"},
        headers={"Authorization":"Beare fake-token"}
    )
    post_data=post_response.json()

    return {
        "get_url": get_data.get("url"),
        "post_json": post_data.get("json"),
        "status_codes": {
            "get": response.status_code,
            "post": post_response.status_code
        }
    }

# ============================================================
# PARALLEL EXTERNAL API CALLS
# ============================================================
@app.get("/http/parallel")
async def parallel_http_call():
    """Call multiple external APIs simultaneously"""
    start=time.perf_counter()

    responses=await asyncio.gather(
        http_client.get("https://httpbin.org/delay/1"),
        http_client.get("https://httpbin.org/delay/1"),
        http_client.get("https://httpbin.org/delay/1"),
        return_exceptions=True
    )

    duration=time.perf_counter()-start

    results=[]
    for r in responses:
        print(f"RESPONSE : {r}")
        if isinstance(r,Exception):
            results.append({"error":str(r)})
        else:
            results.append({"status":r.status_code})
    
    return {
        "results":results,
        "total_time_ms":round(duration)*1000,
        "note": "3 x 1s calls done in parallel — total ~1s not 3s"
    }


# ============================================================
# RETRY LOGIC
# ============================================================
async def http_get_with_retry(url:str,max_retries:int=3,backoff_factor:int=0.5)->httpx.Response:
    """
    Retry failed requests with exponential backoff.
    Essential when calling LLM APIs that occasionally fail.
    """
    last_exception=None
    for attempt in range(1,max_retries+1):
        try:
            print(f"[HTTP] Attempt {attempt}/{max_retries}: {url}")
            response=await http_client.get(url=url,timeout=5.0)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as e:
            last_exception=e
            print(f"[HTTP] Timeout on attempt {attempt}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code<500:
                raise # 4xx errors — don't retry
            last_exception=e
            print(f"[HTTP] Server error {e.response.status_code} on attempt {attempt}")
        except httpx.RequestError as e:
            last_exception=e
            print(f"[HTTP] Request error on attempt {attempt}: {e}")
        
        # Exponential backoff: 0.5s, 1s, 2s, ...
        if attempt<max_retries:
            wait_time=backoff_factor*(2**(attempt-1))
            print(f"[HTTP] Retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
    raise HTTPException(
        status_code=503,
        detail=f"Failed after {max_retries} attempts: {str(last_exception)}"
    )

@app.get("/http/retry")
async def test_retry():
    response=await http_get_with_retry(url="https://httpbin.org/get",max_retries=3)
    return {"status":response.status_code,"retried":True}



# ============================================================
# CIRCUIT BREAKER PATTERN
# ============================================================

class CircuitBreaker:
    """
    Circuit breaker prevents hammering a failing service.
    States:
    CLOSED : normal operations, requests go through.
    OPEN : too many failures, requests blocked immediately.
    HALF OPEN : testing of seervice recovered.
    """
    def __init__(self,failure_threshold:int=5,recovery_timeout:float=30.0,success_threshold:int=2):
        self.failure_threshold=failure_threshold # When to open circuit
        self.recovery_timeout=recovery_timeout  # How long to wait before retry
        self.success_threshold=success_threshold # When to close circuit

        self.failure_count=0 # Track consecutive failures
        self.success_count=0 # Consecutive successes in HALF_OPEN
        self.state="CLOSED"
        self.last_failure_time:Optional[float]=None

    def _should_allow_requests(self)->bool:
        if self.state=="CLOSED":
            return True
        if self.state=="OPEN":
            # Check if recovery timeout passed
            if time.time()-self.last_failure_time>=self.recovery_timeout:
                print("[CB] Moving to HALF_OPEN — testing service")
                self.state="HALF_OPEN"
                return True
            return False
        if self.state=="HALF_OPEN":
            return True
        return False
    
    def _on_success(self):
        self.failure_count=0
        if self.state=="HALF_OPEN":
            self.success_count+=1
            if self.success_count>=self.success_threshold:
                print("[CB] Service recovered — moving to CLOSED")
                self.state="CLOSED"
                self.success_count=0
    
    def _on_failure(self):
        self.failure_count+=1
        self.last_failure_time=time.time()
        if self.state=="HALF_OPEN":
            print("[CB] Still failing — back to OPEN")
            self.state="OPEN"
            self.success_count=0
        elif self.failure_count>=self.failure_threshold:
            print(f"[CB] {self.failure_count} failures — OPENING circuit")
            self.state="OPEN"

    async def call(self,coro)->any:
        if not self._should_allow_requests():
            raise HTTPException(
                status_code=503,
                detail=f"Circuit breaker OPEN — service unavailable. Retry after {self.recovery_timeout}s"
            )
        try:
            result=await coro
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

# Global circuit breaker for OpenAI
openai_circuit_breaker=CircuitBreaker(failure_threshold=3,recovery_timeout=10.0)

async def call_openai_api(prompt:str)->dict:
    """Simulated OpenAI API call — sometimes fails"""
    if random.random()<0.3:
        raise httpx.TimeoutException("OpenAI API timeout")
    await asyncio.sleep(0.5)
    return {"response":f"OpenAI response to {prompt}"}

@app.post("/http/circuit-breaker")
async def test_circuit_breaker(prompt:str):
    try:
        result=await openai_circuit_breaker.call(coro=call_openai_api(prompt))
        return {
            "result":result,
            "circuit_state":openai_circuit_breaker.state,
            "failures":openai_circuit_breaker.failure_count
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    
@app.get("/http/circuit-status")
def circuit_status():
    return {
        "state": openai_circuit_breaker.state,
        "failure_count": openai_circuit_breaker.failure_count,
        "failure_threshold": openai_circuit_breaker.failure_threshold
    }



# ============================================================
# STREAMING HTTP RESPONSE — proxy LLM stream
# ============================================================

async def proxy_stream(url:str):
    """Proxy a streaming response from external API
    Used to : add auth,logging,rate limiting to LLM stream
    """
    async with http_client.stream(method="GET",url=url) as response:
        async for chunk in response.aiter_text():
            print(chunk)
            yield chunk

@app.get("/http/proxt-stream")
async def stream_proxy():
    """Proxy external streaming response through your API"""
    return StreamingResponse(
        proxy_stream("https://httpbin.org/stream/5"),
        media_type="application/json"
    )


# ============================================================
# CALLING REAL LLM APIS — production patterns
# ============================================================
class LLMRequest(BaseModel):
    prompt:str
    model:str="gpt-3.5-turbo"
    max_tokens:int=512

@app.post("/llm/openai")
async def call_real_openai(req:LLMRequest):
    """How to call OpenAI API with httpx directly.
    In production use openai SDK — but this shows the pattern.
    """
    api_key="sk-fake"
    try:
        response=await http_client.post(
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization":f"Bearer {api_key}",
                "Content-Type":"application/json"
            },
            json={
                "model":req.model,
                "messages":[{"role":"user","content":req.prompt}],
                "max_tokens":req.max_tokens
            },
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code==401:
            raise HTTPException(status_code=401,detail="Invalid OpenAI key")
        elif e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="OpenAI rate limit exceeded")
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e.response.text}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAI API timeout")
    



