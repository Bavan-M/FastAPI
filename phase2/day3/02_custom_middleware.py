import time
import uuid
from fastapi import FastAPI,Request,Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import asyncio

app=FastAPI()

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request:Request,call_next):
        start=time.perf_counter()
        response=await call_next(request) # ⬅️ This calls the next middleware/route
        duration=time.perf_counter()-start
        response.headers["X-Process-Time"]=f"{duration:.4f}s"
        print(f"[TIMING] {request.method}:{request.url.path}->{duration:.4f}s")
        return response
    

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request:Request,call_next):
        request_id=request.headers.get("X-Request-ID",str(uuid.uuid4()))
        request.state.request_id=request_id
        response=await call_next(request) # ⬅️ This calls the next middleware/route
        response.headers["X-Request-ID"]=request_id
        return response
    
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request:Request,call_next):
        print(f"[REQUEST] {request.method}:{request.url}")
        print(f"[HEADERS] User-Agent :{request.headers.get('user-agent',"unknown")}")
        response=await call_next(request) #  ⬅️ This calls the next middleware/route
        print(f"[RESPONSE] State: {response.status_code}")
        return response

app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)

@app.get("/")
async def read_root():
    await asyncio.sleep(3)
    return {"message":"Check response headers for X-Process Time and X-Request-ID"}

@app.get("/request-info")
def request_info(request:Request):
    return {
        "request_id":request.state.request_id,
        "method":request.method,
        "url":request.url,
        "headers":request.headers
    }