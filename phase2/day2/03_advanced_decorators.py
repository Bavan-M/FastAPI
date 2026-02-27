from fastapi import FastAPI,HTTPException
import functools
import asyncio
import time

app=FastAPI()

def retry(times:int=3,delay:float=0.5,exception:tuple=(Exception,)):
    def decorators(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            last_exception=None
            for attempt in range(1,times+1):
                try:
                    print(f"[RETRY] Attempt {attempt}/{times} for {func.__name__} ")
                    return await func(*args,**kwargs)
                except exception as e:
                    last_exception=e
                    print(f"[RETRY] Attempt {attempt} failed {last_exception}")
                    if attempt<times:
                        await asyncio.sleep(delay)
            raise HTTPException(status_code=503,detail=f"Service failed after {times} attempts:{str(last_exception)}")
        return wrapper
    return decorators

call_count=0

@app.get("/llm/generate")
@retry(times=3,delay=0.8,exception=(ConnectionError,))
async def llm_call(prompt:str):
    global call_count
    call_count+=1
    if call_count<3:
        raise ConnectionError("LLM API temporarily unavailable")
    
    call_count=0
    return {"prompt":prompt,"response":"Here is the LLM response"}


_cache:dict={}

def cache(ttl_seconds:int=60):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            cache_key=f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            print(cache_key)
            now=time.time()

            if cache_key in _cache:
                result,cached_at=_cache[cache_key]
                print(f"RESULT: {result}")
                print(f"CACHED AT: {cached_at}")
                if now-cached_at<ttl_seconds:
                    print(f"[CACHE] HIT for {func.__name__}")
                    return result
                
            print(f"[CACHE] MISS for {func.__name__} computing.....")
            result=await func(*args,**kwargs)
            _cache[cache_key]=(result,now)
            return result
        return wrapper
    return decorator

@app.get("/emebddings/{text}")
@cache(ttl_seconds=30)
async def get_embeddings(text:str):
    await asyncio.sleep(0.5)
    fake_embeddings=[0.1,0.2,0.3,0.4,0.5]
    return {"text":text,"emebddings":fake_embeddings}


_call_times:dict={}

def rate_limit(max_calls:int=3,window_seconds:int=60):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            key=func.__name__
            now=time.time()

            if key not in _call_times:
                _call_times[key]=[]

            _call_times[key]=[t for t in _call_times[key] if now-t<window_seconds]
            print(_call_times)
            if len(_call_times[key])>=max_calls:
                raise HTTPException(status_code=429,detail=f"Rate limit exceeded:max {max_calls} calls per {window_seconds}")
            
            _call_times[key].append(now)

            return await func(*args,**kwargs)
        return wrapper
    return decorator

@app.get("/ai/summarize")
@rate_limit(max_calls=3)
async def summarize(text:str):
    return {"summary":f"summary of {text[:50]}.........."}

def log_exection_time(func):
    @functools.wraps(func)
    async def wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=await func(*args,**kwargs)
        duration=time.perf_counter()-start
        print(f"[TIMER] {func.__name__} took {duration:.4f}sec")
        return result
    return wrapper

@app.get("/ai/analyze")
@log_exection_time
@cache(ttl_seconds=30)
@retry(times=3)
async def analyze(query:str):
    await asyncio.sleep(0.3)
    return {"query":query,"analysis":"........."}



