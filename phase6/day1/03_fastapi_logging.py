from loguru import logger
import os,sys
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI,Request,Response,HTTPException
import uuid
import time
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

# ============================================================
# LOGGER SETUP
# ============================================================
#Parse ugly JSON in your terminal during development 😖
#Write brittle regex to parse human logs in production 😱
def setup_logger(environment:str="development"):
    logger.configure(extra={"request_id": "-"})
    if environment=="production":
        logger.add(
            sys.stdout,
            level="INFO", # no need to capture all the debug level for prod so we use info also its volumne is less
            serialize=True,
            enqueue=True # Async for production
        )
    else:
        logger.add(
            sys.stdout,
            level="DEBUG",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[request_id]:<8}</cyan> | {message}",
            colorize=True
        )
    script_dir=Path(__file__).parent
    log_dir=script_dir/"logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "api_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file,
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        format="{time} | {level} | {extra} | {message}"
    )

# ============================================================
# LOGGING MIDDLEWARE
# ============================================================
class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Automatically logs every HTTP request with:
    - Unique request ID
    - Method, path, status code
    - Duration
    - User (if authenticated)
    - Request/response size

    Replaces ALL the print() statements from previous phases.
    """
    # Skip logging for these paths (too noisy)
    SKPI_PATHS={"/health","/metrics","/favicon.ico"} # since list is O(n) and for set it is O(1) for finding and maintaining unique
    async def dispatch(self, request:Request, call_next)->Response:
        # Skip noisy endpoints
        if request.url.path in self.SKPI_PATHS:
            return await call_next(request)
        
        # Generate or inherit request ID
        request_id=request.headers.get("X-Request-ID",str(uuid.uuid4())[:8])
        request.state.request_id=request_id

        # Bind request ID to ALL logs in this request context with keyword for automatic cleanup of context log like removing request_id or it will continue for next request
        with logger.contextualize(request_id=request_id):
            start=time.perf_counter()

            # Log incoming request
            logger.bind(
                event="request_start",
                method=request.method,
                path=request.url.path,
                query=str(request.query_params),
                client_ip=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("user-agent","")[:50]
            ).info(f"-> {request.method} {request.url.path}")
            # Process request
            try:
                response=await call_next(request)
                duration=time.perf_counter()-start

                # Choose the log function
                if response.status_code>=500:
                    log_fn=logger.error
                elif response.status_code>=400:
                    log_fn=logger.warning
                else:
                    log_fn=logger.info
                
                logger.bind(
                    event="request_complete",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=round(duration*1000),
                ).log(log_fn.__name__.upper(), f"<- {response.status_code} {request.url.path} ({duration}ms)")

                # Add request ID to response headers
                response.headers["X-Request-ID"]=request_id
                response.headers["X-Process-Time"]=f"{duration:.4f}s"

                return response
            except Exception as e:
                duration=time.perf_counter()-start
                logger.bind(
                    event="request_error",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round(duration*1000),
                    error=str(e)
                ).exception(f"Unhandled error in {request.url.path}")
                raise

# ============================================================
# DOMAIN LOGGERS — import these in your route files
# ============================================================
auth_logger=logger.bind(subsystem="auth")
llm_logger=logger.bind(subsystem="llm")
db_logger=logger.bind(subsystem="database")
ws_logger=logger.bind(subsystem="websocket")


@asynccontextmanager
async def lifespan(app:FastAPI):
    setup_logger(environment=os.getenv("ENV","development"))
    logger.info("Application starting up")
    logger.bind(
        version="1.0.0",
        environment=os.getenv("ENV","development"),
        python_version=sys.version.split()[0]
    ).info("Start up Configuration")
    yield
    logger.info("Application shutting down")


app=FastAPI(title="Fast API Logging demo",lifespan=lifespan)
app.add_middleware(LoggingMiddleware)


# ============================================================
# EXCEPTION HANDLERS — log all errors consistently
# ============================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request:Request,exc:HTTPException):
    request_id=getattr(request.state,"request_id","unknown")
    logger.bind(
        request_id=request_id,
        status_code=exc.status_code,
        path=request.url.path,
        detail=exc.detail
    ).warning(f"HTTP {exc.status_code}:{exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error":exc.detail,"request_id":request_id}
    )

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request:Request,exc:RequestValidationError):
    request_id=getattr(request.state,"request_id","unknown")
    errors=[{"field":str(e["loc"]),"msg":e["msg"]} for e in exc.errors()]

    logger.bind(
        request_id=request_id,
        path=request.url.path,
        errors=errors,
    ).warning("Validation error")

    return JSONResponse(
        status_code=422,
        content={"error":"validation_error","details":errors,"request_id":request_id}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request:Request,exc:Exception):
    request_id=getattr(request.state,"request_id","unknown")
    logger.bind(
        path=request.url.path
    ).exception("Unhandled exception")

    return JSONResponse(
        status_code=500,
        content={"error":"internal_server_error","request_id":request_id}
    )


# ============================================================
# SCHEMAS
# ============================================================
class GenerateRequest(BaseModel):
    prompt:str
    model:str="gpt-4"

# ============================================================
# ROUTES — using domain loggers instead of print()
# ============================================================
@app.post("/auth/login")
async def login(request:Request,username:str,password:str):
    request_id=getattr(request.state,"request_id","unknown")
    if username=="alice" and password=="pass123":
        auth_logger.bind(
            request_id=request_id,
            username=username,
            ip=request.client.host if request.client else "unknown"
        ).info("Login success")
        return {"token":"fake-token","username":username}
    auth_logger.bind(
        request_id=request_id,
        username=username,
        ip=request.client.host if request.client else "unknown"
    ).warning("Login failed")
    raise HTTPException(status_code=401,detail="Invalid creds")

@app.post("/llm/generate")
async def generate(request: Request, req: GenerateRequest):
    request_id = getattr(request.state, "request_id", "unknown")
    import asyncio

    llm_logger.bind(
        request_id=   request_id,
        model=        req.model,
        prompt_length=len(req.prompt)
    ).info("Starting LLM generation")

    start = time.perf_counter()

    try:
        await asyncio.sleep(0.5)   # simulate LLM call
        tokens = len(req.prompt.split()) * 10
        duration = time.perf_counter() - start

        llm_logger.bind(
            request_id= request_id,
            model=      req.model,
            tokens=     tokens,
            duration_ms=round(duration * 1000),
            cost_usd=   round(tokens * 0.00003, 4)
        ).success("LLM generation complete")

        return {
            "response":    f"Response to: {req.prompt[:30]}",
            "model":       req.model,
            "tokens_used": tokens,
            "request_id":  request_id
        }

    except Exception as e:
        llm_logger.bind(
            request_id=request_id,
            model=      req.model,
            error=      str(e)
        ).error("LLM generation failed")
        raise HTTPException(status_code=503, detail="LLM service unavailable")
    

@app.get("/health")
def health():
    # Not logged — excluded from middleware
    return {"status": "ok"}


@app.get("/error-demo")
def error_demo():
    raise ValueError("This is an unhandled exception")



         


