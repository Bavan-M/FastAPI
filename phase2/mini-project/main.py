import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import uuid
import time
import asyncio
import functools
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from core.config import settings
from core.exceptions import AppException
from routers import auth,tasks,admin


def log_execution_time(func):
    @functools.wraps(func)
    async def async_wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=await func(*args,**kwargs)
        duration=time.perf_counter()-start
        print(f"[TIMER] {func.__name__} took {duration:.4f}sec")
        return result
    
    def sync_wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=func(*args,**kwargs)
        duration=time.perf_counter()-start
        print(f"[TIMER] {func.__name__} took {duration:.4f}sec")
        return result
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

@asynccontextmanager
async def lifespan(app:FastAPI):
    print(f"{settings.app_name} v{settings.version} starting...")
    print(f"->In memory store initialzed")
    print(f"Exception handler registered")
    print(f"Middleware stack ready")
    print(f"Accepting requests")

    yield

    print(f"{settings.app_name} shutting down gracefully")
    print("Good Bye")


app=FastAPI(title=settings.app_name,version=settings.version,lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost","127.0.0.1","*.yourdomain.com"]
)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        request_id=request.headers.get("X-Request-ID",str(uuid.uuid4()))
        request.state.request_id=request_id
        response=await call_next(request)
        response.headers['X-Request-ID']=request_id
        return response
    
class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        start=time.perf_counter()
        response=await call_next(request)
        duration=time.perf_counter()-start
        response.headers['X-Response-Time']=f"{duration:.4f}sec"
        print(f"[TIMING] {request.method}{request.url.path}->{duration:.4f}sec")
        return response
    
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        print(f"[REQUEST] {request.method}{request.url.path} | request_id:{request.state.request_id if hasattr(request.state,'request_id') else 'N/A'}")
        response=await call_next(request)
        print(f"[RESPONSE] {response.status_code}")
        return response
    
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(LoggingMiddleware)

def build_error_response(status_code:int,error:str,message:str,details:dict=None,request_id:str=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error":error,
            "message":message,
            "details":details or {},
            "request_id":request_id or str(uuid.uuid4())
        }
    )

@app.exception_handler(AppException)
async def app_exception_handler(request:Request,exc:AppException):
    return build_error_response(
        status_code=exc.staus_code,
        error=exc.error,
        message=exc.message,
        details=exc.details,
        request_id=getattr(request.state,'request_id',None)
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request:Request,exc:RequestValidationError):
    errors=[{"field":"->".join(str(l) for l in error['loc']),"issues":error['msg']} for error in exc.errors()]
    return build_error_response(
        status_code=422,
        error="validation error",
        message="invalid request data",
        details={"error":errors},
        request_id=getattr(request.state,'request_id',None)
    )

@app.exception_handler(Exception)
async def global_exception_handler(request:Request,exc:Exception):
    print(f"[CRITICAL] Unhadled :{exc} , path {request.url.path}")
    return build_error_response(
        status_code=500,
        error="internal_server_error",
        message="Something went wrong .PLease try again later",
        request_id=getattr(request.state,'request_id',None)
    )

app.include_router(router=auth.router,prefix=settings.api_prefix)
app.include_router(router=tasks.router,prefix=settings.api_prefix)
app.include_router(router=admin.router,prefix=settings.api_prefix)


@app.get("/",tags=["health"])
@log_execution_time
async def root():
    return {"app":settings.app_name,"version":settings.version,"docs":"/docs"}

@app.get("/health",tags=["health"])
@log_execution_time
async def health():
    return {"status":"ok","version":settings.version}





    




