import time
import asyncio
from fastapi import FastAPI,HTTPException,Request
import functools

app=FastAPI()

def log_execution_time(func):
    @functools.wraps(func)
    async def async_wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=await func(*args,**kwargs)
        end=time.perf_counter()
        print("async wrapper")
        print(f"[TIMER] {func.__name__} executed in {end-start:.4f} seconds")
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=func(*args,**kwargs)
        end=time.perf_counter()
        print("sync wrapper")
        print(f"[TIMER] {func.__name__} executed in {end-start:.4f} seconds ")
        return result
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper

@app.get("/fast")
@log_execution_time
async def fast_endpoint():
    return {"message":"fast response"}


@app.get("/slow")
@log_execution_time
async def slow_endpoint():
    await asyncio.sleep(2)
    return {"message":"slow response"}

@app.get("/sync")
@log_execution_time
def sync_endpoint():
    return {"message":"sync response"}


def require_roles(*allowed_roles:str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper (*args,**kwargs):
            request:Request=kwargs.get("request")
            role=request.query_params.get("role","user")

            if role not in allowed_roles:
                raise HTTPException(status_code=403,detail=f"{role} not foumd .Allowed roles are {allowed_roles}")
            return await func(*args,**kwargs)
        return wrapper
    return decorator

@app.get("/admin/stats")
@require_roles("admin")
async def admin_stats(request:Request):
    return {"stats":{"users":100,"requests_today":1000}}

@app.get("/reports")
@require_roles("admin","analyst")
async def admin_stats(request:Request):
    return {"reports":["report_1","report_2"]}

def deprecated(message:str="this endpoint is deprecated"):
    def decorater(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            print(f"[DEPRECATION WARNING] {func.__name__}: {message}")
            result=await func(*args,**kwargs)
            return result
        return wrapper
    return decorater

@app.get("/v1/search")
@deprecated("Use v2 search instead")
async def search(query:str):
    return {"query":query,"result":[],"message":"this endpoint is deprecated"}




        


    





