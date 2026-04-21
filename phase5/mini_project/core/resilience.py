import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from typing import Any,Callable
import asyncio
from fastapi import HTTPException
import random
from core.config import settings
from enum import Enum
from dataclasses import dataclass,field
import time
# ============================================================
# TIMEOUT
# ============================================================
async def with_timeout(coro,timeout:float,operation:str="Operation")->Any:
    try:
        return await asyncio.wait_for(
            coro,
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"{operation} timeout after {timeout}"
        )
    

# ============================================================
# RETRY
# ============================================================
def _backoff_delay(attempt:int,base:float)->float:
    """Exponential backoff with jitter"""
    exp=min(base*(2**(attempt-1)),60.0)
    jitter=random.uniform(0,exp*0.1)
    return exp+jitter

async def retry(coro_factory:Callable,max_attempts:int=None,base_delay:float=None,operation:str="Operation")->Any:
    max_attempts=max_attempts or settings.max_retry_attempts
    base_delay=base_delay or settings.retry_base_delay
    last_exc=None

    for attempt in range(1,max_attempts+1):
        try:
            print(f"[RETRY:{operation}] Attempt {attempt}/{max_attempts}")
            return await coro_factory()
        except HTTPException as e:
            if 400<=e.status_code<500 and e.status_code!=429:
                raise
            last_exc=e
        except Exception as e:
            last_exc=e
        if attempt<max_attempts:
            delay=_backoff_delay(attempt=attempt,base=base_delay)
            print(f"[RETRY:{operation}] Failed — waiting {delay:.2f}s")
            await asyncio.sleep(delay=delay)
    
    raise last_exc or HTTPException(status_code=503,detail=f"{operation} failed")


# ============================================================
# CIRCUIT BREAKER
# ============================================================
class CBState(str,Enum):
    CLOSED="closed"
    OPEN="open"
    HALF_OPEN="half_open"


@dataclass
class CircuitBreaker:
    name:str
    failure_threshold:int=None
    recovery_timeout:float=None
    success_threshold:int=2

    state:CBState=field(default=CBState.CLOSED,init=False)
    failure_count:int=field(default=0,init=False)
    success_count:int=field(default=0,init=False)
    last_failre_time:float=field(default=0.0,init=False)
    _lock:asyncio.Lock=field(default=asyncio.Lock(),init=False)

    def __post_init__(self): # extra set up when CircuitBreaker dataclass is called
        self.failure_threshold=self.failure_threshold or settings.cb_failure_threshold
        self.recovery_timeout=self.recovery_timeout or settings.cb_recovery_timeout

    def _can_attempt(self)->bool:
        if self.state==CBState.CLOSED:
            return True
        if self.state==CBState.OPEN:
            if (time.monotonic()-self.last_failre_time)>=self.recovery_timeout:
                self.state=CBState.HALF_OPEN
                self.success_count=0
                print(f"[CB:{self.name}] → HALF_OPEN")
                return True
            return False
        return True
    
    def _on_success(self):
        self.failure_count=0
        if self.state==CBState.HALF_OPEN:
            self.success_count+=1
            if self.success_count>=self.success_threshold:
                self.state=CBState.CLOSED
                self.success_count=0
                print(f"[CB:{self.name}] ✅ → CLOSED")

    
    def _on_failure(self):
        self.failure_count+=1
        self.last_failre_time=time.monotonic()
        if self.state==CBState.HALF_OPEN:
            self.state=CBState.OPEN
            print(f"[CB:{self.name}] ❌ → OPEN")
        elif self.failure_count>=self.failure_threshold:
            self.state=CBState.OPEN
            print(f"[CB:{self.name}] ❌ {self.failure_count} failures → OPEN")


    async def call(self,coro_factory:Callable=None,fallback=None)->Any:
        async with self._lock:
            can_attempt=self._can_attempt

        if not can_attempt:
            print(f"[CB:{self.name}] ⚡ Short-circuit")
            if fallback is not None:
                return fallback() if callable(fallback) else fallback
            raise HTTPException(
                status_code=503,
                detail={
                    "error":"circuit_open",
                    "service":self.name,
                    "retry_after":self.recovery_timeout
                }
            )
        try:
            result=await coro_factory()
            async with self._lock:
                self._on_success()
            return result
        except Exception as e:
            async with self._lock:
                self._on_failure()
            raise

    @property
    def status(self)->dict:
        return {
            "name":self.name,
            "state":self.state,
            "failures":self.failure_count,
            "threshold":self.failure_threshold,
            "retry_in":max(0,self.recovery_timeout-(time.monotonic()-self.last_failre_time)) if self.state==CBState.OPEN else 0
        }
    

openai_cb=CircuitBreaker(name="openai")
groq_cb=CircuitBreaker(name="groq")


            


    