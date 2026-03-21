import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Request
from core.config import settings
from contextlib import asynccontextmanager
from middleware.security import SecurityHeadersMiddleware,RequestIDMiddleware,TimingMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
from core.exceptions import AppException
from fastapi.exceptions import RequestValidationError
from routers import admin,api_keys,auth

@asynccontextmanager
async def lifespan(app:FastAPI):
    print(f"\n🚀 {settings.app_name} v{settings.version} starting...")
    print(f"  → Environment : {settings.environment}")
    print(f"  → Debug       : {settings.debug}")
    print(f"  → OpenAI      : {'✅' if settings.openai_api_key else '❌ not set'}")
    print(f"  → Anthropic   : {'✅' if settings.anthropic_api_key else '❌ not set'}")
    print(f"  → Google OAuth: {'✅' if settings.google_client_id else '❌ not set'}")
    print("✅ Ready!\n")

    yield

    print(f"\n🛑 {settings.app_name} shutting down...")
    print("✅ Goodbye!\n")


app=FastAPI(title=settings.app_name,version=settings.version,lifespan=lifespan,docs_url="/docs",redoc_url="/redoc")

app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH","DELETE"],
    allow_headers=["Authorization","Content-Type","X-API-Key","X-Request-ID"],
    expose_headers=["X-Request-ID","X-Process-Time"]
)


def error_response(status_code:int,error:str,message:str,request_id:str=None,details:dict=None):
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
    return error_response(status_code=exc.status_code,
                          error=exc.error,
                          message=exc.message,
                          details=exc.details,
                          request_id=getattr(request.state,"request_id",None))


@app.exception_handler(RequestValidationError)
async def validation_handler(request:Request,exc:RequestValidationError):
    errors=[{"field":"->".join(str(l) for e in l["loc"]),"issue":e['msg']} for e in exc.error()]
    return error_response(
        status_code=422,
        error="validation error",
        message="Invalid request data",
        details={"errors":errors},
        request_id=getattr(request.state,"request_id",None)
    )


@app.exception_handler(Exception)
async def global_handler(request:Request,exc:Exception):
    return error_response(status_code=500,
                          error="Internal server error",
                          message="SOomething went wrong",
                          request_id=getattr(request.state,"request_id",None))


PREFIX="/api/v1"
app.include_router(router=auth.router,prefix=PREFIX)
app.include_router(router=api_keys.router,prefix=PREFIX)
app.include_router(router=admin.router,prefix=PREFIX)

@app.get("/",tags=["Health"])
def root():
    return {
        "app":settings.app_name,
        "version":settings.version,
        "environment":settings.environment,
        "docs":"/docs"
    }







