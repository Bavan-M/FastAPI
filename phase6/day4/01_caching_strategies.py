import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from typing import Optional,Any
import time
import redis.asyncio as aioredis
import json
import hashlib
from fastapi import Request,FastAPI
import functools
from contextlib import asynccontextmanager
import asyncio
from pydantic import BaseModel

# ============================================================
# CACHE INTERFACE — defines the contract
# ============================================================
class CachedBacked:
    """
    Abstract cache interface.
    This class would be the main parent class which consists of functions which are common to use in Redis,in-memory,PostreSQL
    We are overwriting the functions which we have defined here whenever we are inheriting this class as parent class
    Swap between in-memory and Redis without changing routes.
    """
    async def get(self,key:str)->Optional[Any]:
        raise NotImplementedError
    
    async def set(self,key:str,value:Any,ttl:int=60):
        raise NotImplementedError
    
    async def delete(self,key:str):
        raise NotImplementedError
    
    async def clear_prefix(self,prefix:str):
        raise NotImplementedError
    

# ============================================================
# IN-MEMORY CACHE — for development and single-instance apps
# ============================================================
class InMemoryCache(CachedBacked):
    """
    Simple in-memory cache with TTL.
    Fast, zero dependencies.
    Lost on restart — not shared between instances.
    Use for: development, single-instance deployments.
    """
    def __init__(self):
        self._store:dict={}
        self._hits:int=0
        self._misses:int=0

    async def get(self,key:str)->Optional[Any]:
        try:
            entry=self._store.get(key)
            if not entry:
                self._misses+=1
                return None
            value,entry_at=entry
            if time.time()>entry_at:
                del self._store[key] # del does not returns value and returns error if its not there
                self._misses+=1
                return None
            self._hits+=1
            return value
        except Exception as e:
            return str(e)
    
    async def set(self,key:str,value:Any,ttl:int=60):
        self._store[key]=(value,time.time()+ttl)

    async def delete(self,key:str):
        self._store.pop(key,None) # pop returns the value and returns None if not found

    async def clear_prefix(self, prefix):
        keys=[key for key in self._store if key.startswith(prefix)]
        for key in keys:
            del self._store[key]

    @property
    def stats(self)->dict:
        return {
            "backend":"in_memory",
            "size":len(self._store),
            "hits":self._hits,
            "misses":self._misses,
            "hit_rate":round(self._hits/max(1,self._hits+self._misses)*100,1),
            "store":self._store
        }
    

# ============================================================
# REDIS CACHE — for production multi-instance apps
# ============================================================
class RedisCache(CachedBacked):
    """
    Redis-backed cache.
    Survives restarts, shared between all instances.
    Use for: production, multi-instance deployments.

    In production install: pip install redis[asyncio]
    Then replace InMemoryCache with RedisCache.
    """
    def __init__(self,url:str="redis://localhost:6379"):
        self._url=url
        self._redis=None
        self._hits=0
        self._misses=0

    async def connect(self):
        try:
            self._redis=aioredis.from_url(url=self._url,encoding="utf-8",decode_responses=True) # Tells Redis HOW to convert bytes to strings (utf-8) and Automatically converts bytes → strings
            await self._redis.ping() # wait and check if its connected
            print(f"  ✅ Redis cache connected: {self._url}")
        except Exception as e:
            print(f"  ⚠️  Redis unavailable: {e} — falling back to in-memory")
            self._redis=None
    
    async def close(self):
        if self._redis:
            await self._redis.aclose()

    async def get(self,key:str)->Optional[Any]:
        if not self._redis:
            return None
        try:
            value=await self._redis.get(key)
            if value is None:
                self._misses+=1
                return None
            self._hits+=1
            return json.loads(value)
        except Exception:
            return None
        
    async def set(self,key:str,value:str,ttl:int=60):
        if not self._redis:
            return
        try:
            await self._redis.setex(name=key,time=ttl,value=json.dumps(value))
        except Exception:
            pass

    async def delete(self,key:str):
        if self._redis:
            await self._redis.delete(key)

    async def clear_prefix(self,prefix:str):
        if not self._redis:
            return 
        keys=await self._redis.keys(f"{prefix}")
        if keys:
            await self._redis.delete(*keys)

    @property
    def stats(self)->dict:
        return {
            "backend":"redis",
            "url":self._url,
            "hits":self._hits,
            "misses":self._misses,
            "hit_rate":round(self._hits/max(1,self._hits+self._misses)*100,1)
        }

cache=RedisCache()


# ============================================================
# CACHE KEY BUILDERS
# ============================================================

def make_llm_cache_key(prompt:str,model:str,temperature:float)->str:
    """
    Build a deterministic cache key for LLM responses.
    Same prompt + model + temperature = same cache key = same cached response.
    temperature=0.0 is fully deterministic — great for caching.
    High temperature = random responses — don't cache.
    """
    content=f"{prompt}:{model}:{temperature}"
    return f"llm:{hashlib.sha256(content.encode()).hexdigest()[:16]}" # to search faster we decrease the length to 16

def make_embedding_cache_key(text:str,model:str)->str:
    """
    Embeddings are fully deterministic — same text always gets same embedding.
    Cache aggressively — they're expensive and unchanging.
    """
    content=f"{text}:{model}"
    return f"embed:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

def make_route_cache_key(request:Request)->str:
    """
    Build cache key from HTTP request.
    Used by response cache middleware.
    """
    content=f"{request.method};{request.url.path}:{request.url.query}"
    return f"route:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

# ============================================================
# CACHE DECORATOR — simplest caching pattern
# Use when: You have an expensive function (LLM API, database query, calculation)
# Caches: Just the return value of that specific function
# ============================================================
def cached(ttl:int=60,key_prefix:str=""):
    """
    Decorator that caches function return values.
    Usage:
        @cached(ttl=300, key_prefix="llm")
        async def generate(prompt: str) -> dict:
            ...
    why not background because ,Background runs indepnedeltly and does not returns immediately but decorator awaits untill the result comes
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            key_parts=[key_prefix or func.__name__] # get key_prefix like llm,embed or the name of the function
            key_parts.extend(str(a) for a in args) # add the rest of arguments
            key_parts.extend(f"{k}={v}" for k,v in sorted(kwargs.items()))

            cache_key=hashlib.sha256(":".join(key_parts).encode()).hexdigest()[:16]
            cache_key=f"{key_prefix or func.__name__}:{cache_key}"

            # Try cache first
            cached_value=await cache.get(key=cache_key)
            if cached_value is not None:
                print(f"[CACHE] HIT  {func.__name__} key={cache_key[:12]}")
                return cached_value
            
            # Cache miss — call real function
            print(f"[CACHE] MISS {func.__name__} key={cache_key[:12]}")
            result=await func(*args,**kwargs)

            # Store result
            await cache.set(key=cache_key,value=result,ttl=ttl)
            return result
        
        return wrapper
    return decorator


# ============================================================
# RESPONSE CACHE MIDDLEWARE
# Use when: You want to cache entire API endpoints at the HTTP level
# Caches: The complete HTTP response (status, headers, body)
# ============================================================

class ResponseCachedMiddleware:
    """
    Caches entire HTTP responses.
    Subsequent identical requests return cached response instantly.
    Only caches GET requests with 200 responses.
    """
    def __init__(self,app,cache:CachedBacked,ttl:int=60):
        self.app=app
        self.cache=cache
        self.ttl=ttl

    async def __call__(self,scope,recieve,send):
        if scope["type"]!="http":
            await self.app(scope,recieve,send)
            return
        
        request=Request(scope=scope,receive=recieve)
        if request.method!="GET":
            await self.app(scope,recieve,send)
            return
        
        skip_path={"/health","/ready","/cache/stats"}
        if request.url.path in skip_path:
            await self.app(scope,recieve,send)
            return
        
        cache_key=make_route_cache_key(request=request)

        cached_response=await self.cache.get(key=cache_key)
        if cached_response:
            print(f"[RESPONSE CACHE] HIT {request.url.path}")
            await send(
                {
                    "type":"http.response.start",
                    "status":200,
                    "headers":[
                        (b"content-type",   b"application/json"),
                        (b"x-cache",        b"HIT"),
                        (b"x-cache-key",    cache_key.encode()),
                    ]
                }
            )
            await send(
                {
                    "type":"http.response.body",
                    "body":  json.dumps(cached_response).encode()
                }
            )
            return 
        
        # Cache miss — capture response
        response_body=[]
        response_status=[200]

        async def send_and_capture(message):
            if message["type"]=="http.response.start":
                response_status[0]=message["status"]
                headers=list(message.get("headers",[]))
                headers.append((b"x-cache",b"MISS"))
                await send(
                    {
                        **message,
                        "headers":headers
                    }
                )
            elif message["type"]=="http.response.body":
                body=message.get("body",b"")
                response_body.append(body)
                await send(message)

        await self.app(scope,recieve,send_and_capture)


        # Cache if response was successful
        if response_status[0]==200 and response_body:
            try:
                full_body=b"".join(response_body)
                parsed=json.loads(full_body)
                await self.cache.set(key=cache_key,value=parsed,ttl=self.ttl)
                print(f"[RESPONSE CACHE] STORED {request.url.path}")
            except Exception:
                pass

# ============================================================
# APP SETUP
# ============================================================
@asynccontextmanager
async def lifespan(app:FastAPI):
    await cache.connect()
    print("✅ Cache ready")
    yield
    await cache.close()
    print("✅ Cache cleared")

app=FastAPI(title="Caching startergies",lifespan=lifespan)
app.add_middleware(ResponseCachedMiddleware,cache=cache,ttl=30) # because __init__ of ResponseCachedMiddleware needs cache and ttl

# ============================================================
# SIMULATED SERVICES
# ============================================================
async def call_llm(prompt:str,model:str,temperature:float)->dict:
    """Simulates expensive LLM call"""
    await asyncio.sleep(1.0)
    return{
        "response":f"LLM response to {prompt}",
        "model":model,
        "tokens": len(prompt.split())*10
    }

async def call_embedding_api(text: str, model: str) -> list:
    """Simulates expensive embedding call"""
    await asyncio.sleep(0.5)
    return [0.1, 0.2, 0.3, 0.4, 0.5]


# ============================================================
# CACHED SERVICES
# ============================================================
@cached(ttl=300,key_prefix="llm")
async def generate_cached(prompt:str,model:str,temperature:float)->dict:
    """
    LLM generation with caching.
    temperature=0.0 → deterministic → cache forever
    temperature>0.0 → random → short TTL or no cache
    """
    return await call_llm(prompt=prompt,model=model,temperature=temperature)

@cached(ttl=86400,key_prefix="embed")
async def embed_cache(text:str,model:str="text-embedding-ada-002")->list:
    """
    Embeddings are deterministic — cache aggressively.
    Same text always produces same embedding.
    24 hour TTL — embeddings almost never change.
    """
    return await call_embedding_api(text=text,model=model)

# ============================================================
# ROUTES
# ============================================================

class GenerateRequest(BaseModel):
    prompt:str
    model:str="gpt-4"
    temperature:float=0.0

@app.post("/generate")
async def generate(req:GenerateRequest):
    """
    POST requests aren't cached by response middleware.
    Use the @cached decorator pattern instead.
    """
    start=time.perf_counter()

    # Only cache deterministic (temperature=0) calls
    if req.temperature==0.0:
        result=await generate_cached(prompt=req.prompt,model=req.model,temperature=req.temperature)
        source="cache_or_llm"
    else:
        result=await call_llm(prompt=req.prompt,model=req.model,temperature=req.temperature)
        source="llm_direct"
    duration=time.perf_counter()-start
    return {
        **result,
        "duration_ms":round(duration*1000),
        "cache_source":source,
        "tip":"Call again with same prompt — should be instant"
    }

@app.post("/embed")
async def embed(text:str):
    """Embeddings are always cached — deterministic and expensive"""
    start=time.perf_counter()
    embedding=await embed_cache(text=text)
    duration=time.perf_counter()-start
    return {
        "embedding":embedding,
        "duration-ms":round(duration*1000),
        "tip":"Call again — should be instant (cached 24h)"
    }


@app.get("/cache/stats")
async def cache_stats():
    """View cache performance metrics"""
    if isinstance(cache,RedisCache):
        return cache.stats
    return {
        "backend":"redis"
    }

@app.get("/health")
def health():
    return {"status": "ok"}
 



        
            







        
     

    
