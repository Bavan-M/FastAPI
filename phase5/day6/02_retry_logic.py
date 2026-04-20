import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException
import random
import httpx
import asyncio
import functools
import time
app=FastAPI(title="Retry Logic")

# ============================================================
# RETRY STRATEGIES
# ============================================================
class RetryStratergy:
    """
    Defines HOW to retry — delay calculation strategy.
    """
    @staticmethod
    def fixed(delay:float)->float:
        """Same delay every time: 1s, 1s, 1s"""
        return delay
    
    @staticmethod
    def exponential(attempt:int,base:float=0.5,max_delay:float=60.0)->float:
        """Doubles each time: 0.5s, 1s, 2s, 4s, 8s...
        Most common strategy for external APIs.
        """
        return min(base*(2**(attempt-1)),max_delay)
    
    @staticmethod
    def exponential_jitter(attempt:int,base:float=0.5,max_delay:float=60.0)->float:
        """
        Exponential + random jitter.
        Prevents thundering herd — clients don't all retry at same time.
        Best practice for high-traffic systems.
        """
        exp_delay=min(base*(2**(attempt-1)),max_delay)
        jitter=random.uniform(0,exp_delay*0.1)
        return exp_delay+jitter
    
# ============================================================
# RETRY EXCEPTIONS — what to retry vs what not to
# ============================================================
# Errors worth retrying (transient failures)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Errors NOT worth retrying (permanent failures)
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}


def is_retryable_exception(exc:Exception)->bool:
    """Determine if an exception warrants a retry"""
    if isinstance(exc,HTTPException):
        return exc.status_code in RETRYABLE_STATUS_CODES
    
    if isinstance(exc,httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    
    # Network errors are always retryable
    if isinstance(exc,(httpx.TimeoutException,httpx.ConnectError)):
        return True
    
    # asyncio timeout is retryable
    if isinstance(exc,asyncio.TimeoutError):
        return True
    return False

# ============================================================
# CORE RETRY FUNCTION
# ============================================================
async def retry(coro_factory,max_attempts:int=3,stratergy:str="exponential_jitter",base_delay:float=0.5,max_delay:float=60.0,on_retry=None):
    """
    Retry a coroutine with configurable strategy.

    IMPORTANT: Pass a factory function, not the coroutine itself.
    Coroutines can only be awaited once — you need a fresh one each attempt.

    Usage:
        # Wrong ❌
        result = await retry(call_llm("hello"))

        # Correct ✅
        result = await retry(lambda: call_llm("hello"))
    """
    last_exception=None
    for attempt in range(1,max_attempts+1):
        try:
            print(f"[RETRY] Attempt {attempt}/{max_attempts}")
            # Create fresh coroutine each attempt
            return await coro_factory()
        except Exception as e:
            last_exception=e

            if not is_retryable_exception(e):
                print(f"[RETRY] Non-retryable error: {e} — giving up")
                raise

            if attempt==max_attempts:
                print(f"[RETRY] All {max_attempts} attempts failed")
                break

            # Calculate delay based on strategy
            if stratergy=="fixed":
                delay=RetryStratergy.fixed(delay=base_delay)
            elif stratergy=="exponential":
                delay=RetryStratergy.exponential(attempt=attempt,base=base_delay,max_delay=max_delay)
            else:
                delay=RetryStratergy.exponential_jitter(attempt=attempt,base=base_delay,max_delay=max_delay)
            
            print(f"[RETRY] Attempt {attempt} failed: {e}")
            print(f"[RETRY] Waiting {delay:.2f}s before attempt {attempt + 1}")

            if on_retry:
                await on_retry(attempt,e,delay)
            await asyncio.sleep(delay=delay)

    raise last_exception
    
# ============================================================
# RETRY DECORATOR — cleaner syntax
# ============================================================
def retryable(max_attempts:int=3,stratergy:str="exponential_jitter",base_delay:float=0.5,exceptions:tuple[type[Exception],...]=(Exception)):
     """
    Decorator that adds retry logic to any async function.

    Usage:
        @retryable(max_attempts=3, base_delay=0.5)
        async def call_llm(prompt: str) -> str:
            ...
    """
     
     def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            return await retry(
                coro_factory=lambda : func(*args,**kwargs),
                max_attempts=max_attempts,
                stratergy=stratergy,
                base_delay=base_delay
            )
        return wrapper
     return decorator


# ============================================================
# SIMULATED FLAKY SERVICES
# ============================================================

call_counts = {"llm": 0, "embedding": 0}

async def flakey_llm_call(prompt:str,failed_times:int=2)->str:
    """Fails the first N times, then succeeds"""
    call_counts["llm"]+=1
    if call_counts["llm"]<=failed_times:
        raise httpx.TimeoutException(f"LLM timeout on attempt {call_counts["llm"]}")
    call_counts["llm"]=0
    await asyncio.sleep(0.3)
    return f"LLM response to : {prompt}"

async def rate_limited_service(prompt:str)->str:
    """Simulates rate limiting (429)"""
    call_counts["embedding"]+=1
    if call_counts["embedding"]<=2:
        raise HTTPException(status_code=429,detail="Rate limit exceeded")
    call_counts["embedding"]=0
    await asyncio.sleep(0.5)
    return f"Embeddings for {prompt[:20]}"




# ============================================================
# ROUTES
# ===========================================================
@app.post("/retry/basic")
async def retry_basic(prompt:str):
    """Retry a flaky LLM call"""
    start=time.perf_counter()

    result=await retry(
        coro_factory=lambda: flakey_llm_call(prompt=prompt,failed_times=2),
        max_attempts=3,
        stratergy="exponential_jitter",
        base_delay=0.5,
        max_delay=60
    )

    return {
        "result":result,
        "duration_ms":f"{round((time.perf_counter()-start)*1000)} milliseconds"
    }

@app.post("/retry/rate-limit")
async def retry_rate_limit(prompt:str):
    """Handle 429 rate limits with retry"""
    start=time.perf_counter()

    result=await retry(
        coro_factory=lambda:rate_limited_service(prompt=prompt),
        max_attempts=4,
        stratergy="exponential",
        base_delay=0.5
    )

    return {
        "result":result,
        "duration_ms":f"{round((time.perf_counter()-start)*1000)} milliseconds"
    }

@retryable(max_attempts=3,base_delay=0.3)
async def reliable_llm_call(prompt:str)->str:
    """This function automatically retries on failure"""
    call_counts["llm"]+=1
    if call_counts["llm"]<=1:
        raise httpx.TimeoutException(message="Simulated timeout")
    call_counts["llm"]=0
    await asyncio.sleep(0.2)
    return f"Response : {prompt[:20]}"


@app.post("/retry/decorator")
async def retry_with_decorator(prompt:str):
    """Same retry logic but using the decorator"""
    result=await reliable_llm_call(prompt=prompt)
    return {
        "result":result
    }

@app.post("/retry/stratergies")
async def compare_stratergies(prompt:str):
    """Compare all retry strategies side by side"""
    stratergies=["fixed","exponential","exponential_jitter"]
    results = {}
    for strategy in stratergies:
        delays=[]
        for attempt in range(1,4):
            if strategy=="fixed":
                d=RetryStratergy.fixed(0.5)
            elif strategy=="exponential":
                d=RetryStratergy.exponential(attempt=attempt,base=0.5)
            else:
                d=RetryStratergy.exponential_jitter(attempt=attempt,base=0.5)
            delays.append(round(d*1000))
        results[strategy] = {
            "delays_per_attempt": delays,
            "total_wait": round(sum(delays), 3)
        }
    return {
        "results":results
    }
