import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from enum import Enum
import asyncio
import time
import psutil
from contextlib import asynccontextmanager
from fastapi import FastAPI,Response

class HealthStatus(str,Enum):
    HEALTHY="healthy"
    DEGRADED="degraded"
    UNHEALTHY="unhealthy"

class ComponentStatus(str,Enum):
    UP="up"
    DOWN="down"
    UNKNOWN="unknown"


# ============================================================
# DEPENDENCY HEALTH CHECKERS
# ============================================================
class DatabaseHealthChecker:
    """Checks if database is reachable and responsive"""
    def __init__(self):
        self.connected=False
        self.last_check=0.0
        self.latency_ms=0.0
    
    async def connect(self):
        asyncio.sleep(0.5)
        self.connected=True
        print("  ✅ Database connected")
    
    async def close(self):
        self.connect=False

    async def check(self)->dict:
        if not self.connected:
            return {
                "status":ComponentStatus.DOWN,
                "message":"Not connected"
            }
        try:
            start=time.perf_counter()
            await asyncio.sleep(0.1)
            latency=(time.perf_counter()-start)*1000
            self.latency_ms=latency
            self.last_check=time.time()

            return {
                "status":ComponentStatus.UP,
                "latency_ms":round(self.latency_ms),
                "checked_at":self.last_check
            }
        except Exception as e:
            return {
                "status":ComponentStatus.DOWN,
                "message":str(e)
            }

class RedisHealthChecker:
    def __init__(self):
        self.connected  = False
        self.latency_ms = 0.0

    async def connect(self):
        await asyncio.sleep(0.1)
        self.connected = True
        print("  ✅ Redis connected")

    async def close(self):
        self.connected = False

    async def check(self) -> dict:
        if not self.connected:
            return {"status": ComponentStatus.DOWN, "message": "Not connected"}
        try:
            start   = time.perf_counter()
            await asyncio.sleep(0.002)   # simulate PING
            latency = (time.perf_counter() - start) * 1000
            return {
                "status":     ComponentStatus.UP,
                "latency_ms": round(latency, 2)
            }
        except Exception as e:
            return {"status": ComponentStatus.DOWN, "message": str(e)}
        
class LLMHealthChecker:
    """Checks if LLM provider API is reachable"""

    def __init__(self, provider: str = "openai"):
        self.provider   = provider
        self.available  = True
        self.latency_ms = 0.0

    async def check(self) -> dict:
        if not self.available:
            return {
                "status":   ComponentStatus.DOWN,
                "provider": self.provider,
                "message":  "Circuit breaker open"
            }
        try:
            start   = time.perf_counter()
            await asyncio.sleep(0.1)   # simulate lightweight API ping
            latency = (time.perf_counter() - start) * 1000
            return {
                "status":     ComponentStatus.UP,
                "provider":   self.provider,
                "latency_ms": round(latency, 2)
            }
        except Exception as e:
            return {
                "status":   ComponentStatus.DOWN,
                "provider": self.provider,
                "message":  str(e)
            }
        

# ============================================================
# SYSTEM METRICS
# ============================================================

def get_system_metrics()->dict:
    """
    Get system resource usage.
    Alert if memory or CPU is critically high.
    """
    try:
        # It's a Python library that reads system information (like Task Manager on Windows or top on Linux).
        process=psutil.Process() #  Get current Python process
        return {
            "cpu_percent":psutil.cpu_percent(interval=0.1), # How hard your CPU is working (0-100%) measure over 0.1 seconds
            "memory_percent":psutil.virtual_memory().percent, # Percentage of RAM being used
            "memory_used_mb":round(process.memory_info().rss/1024/1024,1),
            # Get memory details
            # RSS = Resident Set Size (actual RAM used) rss is in BYTES (e.g., 157286400 bytes)
            # Divide by 1024 to get KB, divide by 1024 again to get MB
            "open_files":len(process.open_files()), # How many files your app currently has open
            "threads":process.num_threads(), #Number of active threads in your app
            "disk_usage_percent":psutil.disk_usage("/").percent # How full your hard drive is "/" means the main disk (C:\ on Windows, / on Linux)
        }
    except Exception:
        return {}


# ============================================================
# HEALTH MANAGER — orchestrates all checks
# ============================================================
class HealthManager:
    def __init__(self):
        self.db=DatabaseHealthChecker()
        self.redis=RedisHealthChecker()
        self.llm=LLMHealthChecker()

        self.startup_complete=False
        self.startup_time=time.time()
        self.is_shutting_down=False

        self.recent_error=[]

    async def startup(self):
        """Initialize all dependencies"""
        await asyncio.gather(
            self.db.connect(),
            self.redis.connect()
        )
        self.startup_complete=True
    
    async def shutdown(self):
        self.is_shutting_down=True
        await asyncio.gather(
            self.db.close(),
            self.redis.close()
        )
    
    @property
    def uptime_seconds(self)->float:
        return round(time.time()-self.startup_time,1)
    
    async def get_full_health(self)->dict:
        """Full health report — all components checked"""
        db_health=await self.db.check()
        redis_health=await self.redis.check()
        llm_health=await self.llm.check()
        system=get_system_metrics()

        # Determine overall status
        critical_down=(
            db_health["status"]==ComponentStatus.DOWN or redis_health["status"]==ComponentStatus.DOWN
        )
        llm_down=llm_health["status"]==ComponentStatus.DOWN

        # High resource usage = degraded
        memory_high=system.get("memory_percent",0)>90
        cpu_high=system.get("cpu_percent",0)>95

        if critical_down:
            overall=HealthStatus.UNHEALTHY
        elif llm_down or memory_high or cpu_high:
            overall=HealthStatus.DEGRADED
        else:
            overall=HealthStatus.HEALTHY

        return {
            "status":overall,
            "uptime":self.uptime_seconds,
            "version":os.getenv("VERSION","1.0.0"),
            "environment":os.getenv("ENV","production"),
            "components":{
                "database":db_health,
                "redis":redis_health,
                "llm":llm_health
            },
            "system":system,
            "checks_at":time.time()
        }

health_manager=HealthManager()


@asynccontextmanager
async def lifespan(app:FastAPI):
    print("\n🚀 Starting up...")
    await health_manager.startup()
    print("✅ All dependencies ready\n")
    yield
    print("\n🛑 Shutting down...")
    await health_manager.shutdown()

app=FastAPI(title="Health Endpoints Demo",lifespan=lifespan)

# ============================================================
# HEALTH ENDPOINTS
# ============================================================
@app.get("/health",tags=["Health"])
async def liveness():
    """
    LIVENESS probe — Kubernetes: should I restart this pod?

    Returns 200: app process is alive and event loop is running
    Returns 503: only if app is completely hung (should rarely happen)

    Keep this FAST and SIMPLE — no DB checks.
    If this endpoint is slow, liveness probe times out and pod restarts.
    """
    return {
        "status":"alive",
        "uptime":health_manager.uptime_seconds
    }


@app.get("/ready",tags=["Health"])
async def readiness(response:Response):
    """
    READINESS probe — Kubernetes: should I send traffic to this pod?

    Returns 200: pod is ready to handle requests
    Returns 503: pod should be removed from load balancer rotation

    Check all dependencies here — DB, Redis, etc.
    During startup and shutdown → return 503.
    """
    if not health_manager.startup_complete:
        response.status_code=503
        return {
            "status":"not_ready",
            "reason":"still_starting",
            "uptime":health_manager.uptime_seconds
        }
    
    if health_manager.is_shutting_down:
        response.status_code=503
        return {
            "status":"not_ready",
            "reason":"shutting_down",
            "uptime":health_manager.uptime_seconds
        }
    
    # Check critical dependencies
    db_health=await health_manager.db.check()
    redis_health=await health_manager.redis.check()

    if db_health["status"]==ComponentStatus.DOWN:
        response.status_code = 503
        return {
            "status":    "not_ready",
            "reason":    "database_unavailable",
            "database":  db_health
        }
    
    if redis_health["status"]==ComponentStatus.DOWN:
        response.status_code = 503
        return {
            "status": "not_ready",
            "reason": "redis_unavailable",
            "redis":  redis_health
        }
    
    return {
        "status":"ready",
        "database":db_health["status"],
        "redis":redis_health["status"],
        "uptime":health_manager.uptime_seconds
    }



@app.get("/startup", tags=["Health"])
async def startup_probe(response: Response):
    """
    STARTUP probe — Kubernetes: has the app finished initializing?

    Kubernetes waits for this before starting liveness/readiness probes.
    Critical for apps that load ML models (can take 30s-5min).
    Set failureThreshold high enough for your startup time.
    """
    if not health_manager.startup_complete:
        response.status_code = 503
        return {
            "status": "starting",
            "uptime": health_manager.uptime_seconds,
            "tip":    "Startup probe — waiting for initialization"
        }

    return {
        "status": "started",
        "uptime": health_manager.uptime_seconds
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health(response: Response):
    """
    Full health report — for monitoring dashboards and alerts.
    NOT used by Kubernetes probes — too slow for that.
    Called by: Datadog, Grafana, PagerDuty, human operators.
    """
    health = await health_manager.get_full_health()

    # Set HTTP status based on overall health
    if health["status"] == HealthStatus.UNHEALTHY:
        response.status_code = 503
    elif health["status"] == HealthStatus.DEGRADED:
        response.status_code = 207   # Multi-Status (partial success)

    return health


@app.get("/metrics", tags=["Health"])
async def metrics():
    """
    Prometheus-compatible metrics endpoint.
    In production use prometheus-fastapi-instrumentator.
    """
    system = get_system_metrics()
    return {
        "uptime_seconds":     health_manager.uptime_seconds,
        "cpu_percent":        system.get("cpu_percent", 0),
        "memory_percent":     system.get("memory_percent", 0),
        "memory_used_mb":     system.get("memory_used_mb", 0),
        "startup_complete":   health_manager.startup_complete,
        "is_shutting_down":   health_manager.is_shutting_down
    }



# Admin routes for testing
@app.post("/admin/simulate/db-down",tags=["Admin"])
def simulate_db_down():
    health_manager.db.connected=False
    return {
        "message":"Database marked as down - check/ready"
    }

@app.post("/admin/simulate/db-up", tags=["Admin"])
def simulate_db_up():
    health_manager.db.connected = True
    return {"message": "Database marked as up — check /ready"}


@app.post("/admin/simulate/llm-down", tags=["Admin"])
def simulate_llm_down():
    health_manager.llm.available = False
    return {"message": "LLM marked as down — check /health/detailed"}


@app.get("/health")
def health():
    return {"status": "ok"}