import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException
from enum import Enum
from dataclasses import dataclass,field
import asyncio
import time
from typing import Callable,Optional
from contextlib import asynccontextmanager

class CircuitState(str,Enum):
    CLOSED = "closed"
    OPEN ="open"
    HALF_OPEN = "half_open"

# ============================================================
# CIRCUIT BREAKER
# ============================================================
@dataclass
class CircuitBreaker:
    """
    Production-grade circuit breaker for external service calls.
    Thread-safe via asyncio.Lock.
    """
    # These are like settings you choose when installing the breaker
    name:str
    failure_threshold:int=5
    recovery_timeout:float=30.0
    success_threshold:int=2
    timeout:float=10.0

    # These are like readings that change as the breaker works
    state:CircuitState=field(default=CircuitState.CLOSED,init=False)
    failure_count:int=field(default=0,init=False)
    success_count:int=field(default=0,init=False)
    last_failure_time:float=field(default=0.0,init=False)
    total_requests:int=field(default=0,init=False)
    total_failures:int=field(default=0,init=False)
    total_short_circuits:int=field(default=0,init=False)
    _lock:asyncio.Lock=field(default=asyncio.Lock(),init=False)

    def _can_attempt(self)->bool:
        """Should we allow this request through?"""
        print(self.state)
        if self.state==CircuitState.CLOSED:
            return True
        if self.state==CircuitState.OPEN:
            print(self.state)
            elapsed=time.monotonic()-self.last_failure_time
            print(elapsed)
            if elapsed>=self.recovery_timeout:
                print(f"[CB:{self.name}] Recovery timeout passed → HALF_OPEN")
                self.state=CircuitState.HALF_OPEN
                self.success_count=0
                return True
            return False
        
        elif self.state==CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def _record_success(self):
        """Called when a request succeeds"""
        self.failure_count=0
        if self.state==CircuitState.HALF_OPEN:
            self.success_count+=1
            print(f"[CB:{self.name}] Success in HALF_OPEN ({self.success_count}/{self.success_threshold})")

            if self.success_count>self.success_threshold:
                print(f"[CB:{self.name}] ✅ Service recovered → CLOSED")
                self.state=CircuitState.CLOSED
                self.success_count=0

    def _record_failure(self,error:Exception):
        """Called when a request fails"""
        self.failure_count+=1
        self.total_failures+=1
        self.last_failure_time=time.monotonic()

        if self.state==CircuitState.HALF_OPEN:
            print(f"[CB:{self.name}] ❌ Still failing in HALF_OPEN → OPEN")
            self.state=CircuitState.OPEN
            self.success_coun=0

        if (self.state==CircuitState.CLOSED and self.failure_count>=self.failure_threshold):
            print(f"[CB:{self.name}] ❌ {self.failure_count} failures → OPEN")
            self.state=CircuitState.OPEN


    async def call(self,coro_factory:Callable,fallback=None):
        """
        Execute a function through the circuit breaker.
        Pass a factory (lambda) not a coroutine.
        """
        async with self._lock:
            can_attempt=self._can_attempt()
        self.total_requests+=1
        print(can_attempt)

        if not can_attempt:
            self.total_short_circuits+=1
            print(f"[CB:{self.name}] ⚡ Short-circuit — returning immediately")

            if fallback is not None:
                if callable(fallback):
                    return fallback()
                else:
                    return fallback
                
            raise HTTPException(
                status_code=503,
                detail={
                    "error":"circuit_open",
                    "service":self.name,
                    "message":f"Service '{self.name}' is unavailable",
                    "retry_after":self.recovery_timeout,
                    "state":self.state
                }
            )
        try:
            result=await asyncio.wait_for(
                coro_factory(),
                timeout=self.timeout
            )
            async with self._lock:
                self._record_success()
            return result
        
        except Exception as exc:
            async with self._lock:
                self._record_failure(exc)
                raise
        
    @property
    def stats(self)->dict:
        return{
            "name":self.name,
            "state":self.state,
            "failure_count":self.failure_count,
            "failure_threshold":self.failure_threshold,
            "total_requests":self.total_requests,
            "total_failures":self.total_failures,
            "total_short_circuits":self.total_short_circuits,
            "recovery_timeout":self.recovery_timeout,
            "seconds_until_retry":max(0,(time.monotonic()-self.last_failure_time)) if self.state==CircuitState.OPEN else 0
        }
    

# ============================================================
# CIRCUIT BREAKER REGISTRY
# Manage multiple breakers for different services
# ============================================================
class CircuitBreakerRegistry:
    """
    Central registry for all circuit breakers.
    One breaker per external service.
    """
    def __init__(self):
        self._breaker:dict={}
    
    def regsiter(self,cb:CircuitBreaker)->CircuitBreaker:
        self._breaker[cb.name]=cb
        return cb
    
    def get(self,name:str)->Optional[CircuitBreaker]:
        return self._breaker.get(name)
    
    def get_all_stats(self)->dict:
        return {name:cb.stats for name,cb in self._breaker.items()}
    
register=CircuitBreakerRegistry()

openai_cb=register.regsiter(
    CircuitBreaker(
        name="openai",
        failure_threshold=3,
        recovery_timeout=15.0,
        timeout=10.0
    )
)

anthropic_cb=register.regsiter(
    CircuitBreaker(
        name="anthropic",
        failure_threshold=3,
        recovery_timeout=15.0,
        timeout=12.0
    )
)

vector_db_cb=register.regsiter(
    CircuitBreaker(
        name="vector_db",
        failure_threshold=5,
        recovery_timeout=10.0,
        timeout=5.0
    )
)

# ============================================================
# SIMULATED SERVICES — controllable failure rates
# ============================================================
service_health={
    "openai":True,
    "anthropic":True,
    "vector_db":True
}

async def call_openai_api(prompt:str)->dict:
    await asyncio.sleep(0.3)
    if not service_health["openai"]:
        raise ConnectionError("Open AI service unreachable")
    return {
        "model":"gpt-4o","response":f"GTP-4O :{prompt[:30]}"
    }

async def call_anthropic_api(prompt:str)->dict:
    await asyncio.sleep(0.3)
    if not service_health["anthropic"]:
        raise ConnectionError("Anthropic AI service unreachable")
    return {
        "model":"claude-3","response":f"Claude :{prompt[:30]}"
    }

async def call_vector_api(query:str)->list:
    await asyncio.sleep(0.3)
    if not service_health["vector_db"]:
        raise ConnectionError("Vector DB unreachable")
    return [{"text":f"Relevant chunks for {query}","score":0.95}]


# ============================================================
# APP + ROUTES
# ============================================================
@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ Circuit breaker demo ready")
    yield

app=FastAPI(title="Circuit Breaker",lifespan=lifespan)

@app.post("/generate")
async def generate(prompt:str):
    """
    Generate with circuit breaker protection.
    Falls back to Anthropic if OpenAI circuit is open.
    """
    # Try OpenAI first (with circuit breaker)
    try:
        result=await openai_cb.call(
            lambda : call_openai_api(prompt=prompt)
        )
        # Here's what happens:
        # 1. Python sees lambda: make_api_call(user_id) ← NO parentheses on make_api_call
        # 2. This creates a function that says "I'll call this later"
        # 3. Python calls breaker.call() with this function
        # 4. INSIDE breaker.call, it does coro_factory() ← NOW the parentheses happen
        # 5. The API call starts HERE, after the circuit breaker checks
        return {**result,"circuit_stats":openai_cb.stats}
    except HTTPException as e:
        if e.status_code==503:
            print("[FALLBACK] OpenAI unavailable → trying Anthropic")
            try:
                result=await anthropic_cb.call(
                    lambda : call_anthropic_api(prompt=prompt)
                )
                return {
                    **result,
                    "fallback":True,
                    "reason":"openai_circuit_open",
                    "circuit_stats":anthropic_cb.stats
                }
            except HTTPException:
                pass

    return {
        "response": "All AI services temporarily unavailable. Please try again shortly.",
        "degraded": True,
        "openai_state": openai_cb.state,
        "anthropic_state": anthropic_cb.state
    }
    
                
@app.post("/rag/search")
async def rag_search(query:str):
    """Vector search with circuit breaker"""
    try:
        chunks=await vector_db_cb.call(
            lambda : call_vector_api(query=query), # first it calls vector_db_call and inside it calls the call_vector_api
            fallback=[]
        )
        return {
            "query":query,
            "chunks":chunks,
            "circuit_stats":vector_db_cb.stats
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    
# ============================================================
# ADMIN ROUTES — control service health for testing
# ============================================================

@app.post("/admin/service/{service}/break")
def break_service(service: str):
    """Simulate a service going down"""
    if service not in service_health:
        raise HTTPException(status_code=404, detail="Unknown service")
    service_health[service] = False
    return {"service": service, "status": "broken — call it to trip the circuit breaker"}


@app.post("/admin/service/{service}/restore")
def restore_service(service: str):
    """Simulate a service recovering"""
    if service not in service_health:
        raise HTTPException(status_code=404, detail="Unknown service")
    service_health[service] = True
    return {"service": service, "status": "restored"}


@app.get("/admin/circuits")
def get_circuit_stats():
    """View all circuit breaker states"""
    return register.get_all_stats()


@app.post("/admin/circuits/{name}/reset")
def reset_circuit(name: str):
    """Manually reset a circuit breaker"""
    cb = register.get(name)
    if not cb:
        raise HTTPException(status_code=404, detail="Circuit breaker not found")
    cb.state = CircuitState.CLOSED
    cb.failure_count = 0
    cb.success_count = 0
    return {"name": name, "state": cb.state, "message": "Circuit reset to CLOSED"}
