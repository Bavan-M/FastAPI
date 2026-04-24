import os,sys
sys.path.insert(0,os.path.dirname(__file__))
import asyncio
import time
from fastapi import FastAPI,Request,HTTPException
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# ============================================================
# APPLICATION STATE TRACKER
# ============================================================
class AppState:
    """Tracks application health and active work.
    Used to make shutdown decisions.
    """
    def __init__(self):
        self.is_shutting_down:bool=False
        self.is_ready:bool=False
        self.active_requests:int=0
        self.active_tasks:set[asyncio.Task]=set()
        self.startup_time:float=time.time()
        self._shutdown_event:asyncio.Event=asyncio.Event() # it should be private because # TRIGGERS SHUTDOWN from anywhere! 💀

    def register_task(self,task:asyncio.Task):
        """Track a background task so we can wait for it on shutdown"""
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard) # when the task is done call the function

    async def wait_for_shutdown(self):
        await self._shutdown_event.wait()


    def trigger_shutdown(self):
        self._shutdown_event.set() # Because set() on an Event is INSTANT - no waiting needed.
        self.is_shutting_down=True

    @property
    def uptime_seconds(self)->float:
        return round(time.time()-self.startup_time,1)
    
    @property
    def status(self)->dict:
        return {
            "is_ready":self.is_ready,
            "is_shutting_down":self.is_shutting_down,
            "active_requests":self.active_requests,
            "pending_tasks":len(self.active_tasks),
            "uptime_seconds":self.uptime_seconds
        }
    
state=AppState()

# ============================================================
# RESOURCE MANAGERS
# ============================================================
class DatabasPool:
    """Simulates a DB connection pool"""
    def __init__(self):
        self.connected=False
        self.connections=0

    async def connect(self):
        await asyncio.sleep(0.5)
        self.connected=True
        self.connections=10
        print("  ✅ Database pool connected (10 connections)")

    async def close(self):
        await asyncio.sleep(0.5)
        self.connected=False
        self.connections=0
        print("  ✅ Database pool closed cleanly")

class RedisClient:
    def __init__(self):
        self.connected = False

    async def connect(self):
        await asyncio.sleep(0.1)
        self.connected = True
        print("  ✅ Redis connected")

    async def close(self):
        await asyncio.sleep(0.1)
        self.connected = False
        print("  ✅ Redis closed cleanly")

class BackgroundWorker:
    """
    Manages long-running background processes that need to:
    - Start automatically with your FastAPI app
    - Run continuously (polling APIs, processing queues, cleaning databases)
    - Stop gracefully without losing work when the app shuts down
    - Properly cancel tasks to avoid memory leaks
    
    REAL-WORLD USE CASES:
    - Email queue processor: Send pending emails every 10 seconds
    - Database cleaner: Delete expired sessions/tokens every hour
    - External API poller: Fetch data from third-party APIs
    - Analytics aggregator: Collect and batch analytics events
    - File watcher: Monitor directories for new files to process
    - Message consumer: Process RabbitMQ/Kafka messages
    
    This pattern ensures background work:
    1. Doesn't block the main FastAPI event loop
    2. Can be stopped safely during application shutdown
    3. Properly cleans up resources when done
    """
    def __init__(self):
        self.running=False
        self._task:asyncio.Task=None

    async def start(self):
        self.running=True
        self._task=asyncio.create_task(self._run())
        print("  ✅ Background worker started")

    async def _run(self):
        counter=0
        while self.running:
            counter+=1
            await asyncio.sleep(5) # it could be anything as mentioned above in descripiton
            print(f"  [Worker] Heartbeat #{counter}")

    async def stop(self):
        self.running=False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("  ✅ Background worker stopped")

db=DatabasPool()
redis=RedisClient()
worker=BackgroundWorker()

# ============================================================
# LIFESPAN — the heart of graceful shutdown
# ============================================================
@asynccontextmanager
async def lifespan(app:FastAPI):
    # ===== STARTUP =====
    print("\n🚀 Starting up...")

    # Initialize all resources concurrently
    await asyncio.gather(db.connect(),redis.connect())

    # Start background worker
    await worker.start()

    # Mark app as ready to serve traffic
    state.is_ready=True
    print(f"✅ App ready after {state.uptime_seconds}s\n")

    yield # App serves requests here

    # ===== SHUTDOWN =====
    print("\n🛑 Graceful shutdown initiated...")

    # Step 1 — Stop accepting new requests
    state.is_shutting_down=True
    state.is_ready=False
    print("  → No longer accepting new requests")

    # Step 2 — Wait for in-flight requests to complete
    # Give them up to 30 seconds to finish
    shutdown_timeout=30.0
    waited=0.0

    while state.active_requests>0 and waited<shutdown_timeout:
        print(f"  → Waiting for {state.active_requests} active requests... ({waited:.0f}s)")
        await asyncio.sleep(1.0)
        waited+=1

    if state.active_requests>0:
        print(f"  ⚠️  Forcing shutdown — {state.active_requests} requests still active")
    else:
        print("  ✅ All requests completed")

    # Step 3 — Wait for background tasks
    if state.active_tasks:
        print(f"  → Waiting for {len(state.active_tasks)} background tasks...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*state.active_tasks,return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print("  ⚠️  Some tasks did not complete in time")

    # Step 4 — Stop background worker
    await worker.stop()

    # Step 5 — Close all connections cleanly
    await asyncio.gather(
        db.close(),
        redis.close()
    )
    print(f"✅ Shutdown complete after {state.uptime_seconds}s\n")


# ============================================================
# SHUTDOWN MIDDLEWARE
# ============================================================
class ShutdownMiddleware(BaseHTTPMiddleware):
    """
    Tracks active requests.
    Rejects new requests during shutdown.
    """
    async def dispatch(self, request:Request, call_next):
        # Reject during shutdown (except health checks)
        if state.is_shutting_down and request.url.path not in ("/health","/ready"):
            return JSONResponse(
                status_code=503,
                content={
                    "error":"service_unavailabe",
                    "message":"Server is shutting down. Please retry"
                },
                headers={"Retry-After":"5"}
            )
        # Track active request count
        state.active_requests+=1
        try:
            response=await call_next(request)
            return response
        finally:
            state.active_requests-=1


app=FastAPI(title="Graceful shutdown demo",lifespan=lifespan)
app.add_middleware(ShutdownMiddleware)

# ============================================================
# HEALTH + READINESS ENDPOINTS
# ============================================================

# Think of a new employee joining a company:
# Probe	    Question	                    When K8s Asks
# /startup	"Have you finished onboarding?"	Only during first few minutes
# /ready	"Can you take work right now?"	Continuously
# /health	"Are you still alive?"	        Continuously
@app.get("/health")
def health():
    """
        /health endpoint - Liveness probe
        Tells Kubernetes: "Is my app process still running?"
        - Returns 200 even during graceful shutdown (app is alive, just closing)
        - Returns 503 ONLY if app crashed or is completely frozen
        - If this fails, Kubernetes RESTARTS the pod immediately
    """
    return{
        "status":"alive",
        "uptime":state.uptime_seconds
    }

@app.get("/ready")
def readiness():
    """
    Readiness probe — is the app ready to receive traffic?
    Kubernetes calls this to know if it should send traffic.
    Returns 503 during startup (resources not ready) and shutdown.
    Load balancer removes pod from rotation when this returns 503.
    """
    if not state.is_ready or state.is_shutting_down:
        raise HTTPException(
            status_code=503,
            detail={
                "status":"not_ready",
                "is_ready":state.is_ready,
                "shutting_down":state.is_shutting_down
            }
        )
    if not db.connected or not redis.connected:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "dependencies_unavailable",
                "db":     db.connected,
                "redis":  redis.connected
            }
        )
    
    return {
        "status":"ready",
        "db":db.connected,
        "redis":redis.connected,
        "uptime":state.uptime_seconds
    }

@app.get("/startup")
def startup_probe():
    """
    Startup probe — has the app finished initializing?
    Kubernetes waits for this before starting liveness/readiness checks.
    Important for apps that take a long time to load (ML models etc.)
    """
    if not state.is_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status":"starting","uptime":state.uptime_seconds
            }
        )
    return {
        "status":"started","uptime":state.uptime_seconds
    }

@app.get("/status")
def full_status():
    """Detailed status — for monitoring dashboards"""
    return {
        **state.status,
        "dependencies": {
            "database": db.connected,
            "redis":    redis.connected,
            "worker":   worker.running
        }
    }


# ============================================================
# ROUTES
# ============================================================

class GenerateRequest(BaseModel):
    prompt: str
    delay:  float = 2.0   # simulate LLM latency


@app.post("/generate")
async def generate(req:GenerateRequest):
    """Simulates a slow LLM call — tests graceful shutdown"""
    if not state.is_ready:
        raise HTTPException(status_code=503,detail="Service not ready")
    
    print(f"[REQUEST] Starting generation (will take {req.delay}s)...")

    #Simulate slow LLM call
    await asyncio.sleep(req.delay)

    print(f"[REQUEST] Generation complete")
    return {
        "response": f"Generated: {req.prompt[:30]}",
        "delay":    req.delay
    }


@app.post("/background-task")
async def start_background_task():
    """
    Start a long-running background task.
    Graceful shutdown waits for it to complete.
    """
    async def long_task():
        print("[TASK] Background task started")
        await asyncio.sleep(5.0)
        print("[TASK] Background task completed")
    task=asyncio.create_task(long_task())
    state.register_task(task)
    return {"message": "Background task started", "tracked": True}



