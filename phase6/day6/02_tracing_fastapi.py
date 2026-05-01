import os,sys
sys.path.insert(0,os.path.dirname(__file__))

import time
import asyncio
from opentelemetry import trace,metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter,BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader,ConsoleMetricExporter
from opentelemetry.trace import StatusCode
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI,Request
from contextlib import asynccontextmanager
from pydantic import BaseModel
# ============================================================
# TELEMETRY SETUP
# ============================================================
def setup_telemetry(service_name:str="genai-api"):
    """
    Initialize tracing and metrics.
    Call once at application startup.
    """
    resource=Resource.create(attributes={
        "service.name":service_name,
        "service.version":"1.0.0",
        "deployement.environment":os.getenv("ENV","development")
    })

    # --- Tracing ---
    tracer_provider=TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor=BatchSpanProcessor(span_exporter=ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider=tracer_provider)

    # --- Metrics ---
    metric_reader=PeriodicExportingMetricReader(exporter=ConsoleMetricExporter(),export_interval_millis=10000)
    meter_provider=MeterProvider(metric_readers=[metric_reader],resource=resource)
    metrics.set_meter_provider(meter_provider=meter_provider)

    return (
        trace.get_tracer(service_name),
        metrics.get_meter(service_name)
    )

tracer,meter=setup_telemetry()

# ============================================================
# METRICS INSTRUMENTS
# ============================================================
http_requests_total=meter.create_counter(name="http_requests_total",description="Total HTTP requests")
http_request_duraton=meter.create_histogram(name="http_request_duration_ms",description="HTTP request duration in ms",unit="ms")
llm_calls_total=meter.create_counter(name="llm_calls_total",description="Total LLM API calls")
llm_tokens_used=meter.create_histogram(name="llm_tokens_used",description="Tokens per LLM call")
llm_cost_usd=meter.create_histogram(name="llm_cost_usd",description="Cost per LLM call in USD",unit="usd")
active_requests=meter.create_up_down_counter(name="active_requests",description="Currently active requests")

# ============================================================
# TELEMETRY MIDDLEWARE
# ============================================================
class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    Adds tracing and metrics to every HTTP request.
    Works alongside FastAPIInstrumentor for extra context.
    """
    SKIP_PATHS={"/health","/ready","/metrics"}

    async def dispatch(self, request:Request, call_next):
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start=time.perf_counter()
        path=request.url.path
        method=request.method

        active_requests.add(amount=1,attributes={"method":method,"path":path})

        # Get current span (created by FastAPIInstrumentor)
        # Add extra attributes to it
        current_span=trace.get_current_span()
        current_span.set_attribute(
            key="http.client_ip",
            value=request.headers.get("X-Forwarded-For",request.client.host if request.client else "unknown")
        )
        current_span.set_attribute(
            key="http.user_agent",
            value=request.headers.get("user-agent","")[:100]
        )
        try:
            response=await call_next(request)
            duration=(time.perf_counter()-start)*1000

            # Record metrics
            labels={
                "method":method,
                "path":path,
                "status_code":str(response.status_code)
            }
            http_requests_total.add(amount=1,attributes=labels)
            http_request_duraton.record(amount=round(duration),attributes=labels)

            # Mark slow requests in trace
            if duration>2000:
                current_span.add_event(name="slow_request_detected",
                                       attributes={"duration_ms":round(duration),"threshold_ms":2000})
                current_span.set_attribute("request.slow",True)
            response.headers["X-Trace-ID"]=format(current_span.get_span_context().trace_id,"032x")
            return response
        except Exception as e:
            current_span.record_exception(exception=e)
            current_span.set_status(StatusCode.ERROR,str(e))
            raise
        finally:
            active_requests.add(amount=-1,attributes={"method":method,"path":path})


# ============================================================
# TRACING HELPERS FOR LLM CALLS
# ============================================================
class LLMTracer:
    """
    Wraps LLM calls with tracing.
    Records model, tokens, cost, latency as span attributes.
    Makes LLM calls visible in your tracing dashboard.
    """
    def __init__(self,tracer:trace.Tracer):
        self.tracer=tracer

    async def traced_call(self,model:str,prompt:str,call_fn,)->dict: # the actual LLM call coroutine factory
        with self.tracer.start_as_current_span(name=f"llm.{model}",kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("llm.model",model)
            span.set_attribute("llm.prompt_length",len(prompt))
            span.set_attribute("llm.system","Openai")

            span.add_event("llm_call_started")
            start=time.perf_counter()
            try:
                result=await call_fn()
                duration=(time.perf_counter()-start)*1000

                span.add_event("llm_call_completed")
                span.set_attribute("llm.tokens_used",result.get("tokens_used",0))
                span.set_attribute("llm.cost_used",result.get("cost_used",0))
                span.set_attribute("llm.latency_ms",round(duration))
                span.set_status(StatusCode.OK)

                # Record metrics
                llm_calls_total.add(amount=1,attributes={"model":model,"status":"success"})
                llm_tokens_used.record(amount=result.get("tokens_used",0),attributes={"model":model})
                llm_cost_usd.record(amount=result.get("cost_used",0),attributes={"model":model})

                return result
            except Exception as e:
                span.record_exception(exception=e)
                span.set_status(StatusCode.ERROR,description=str(e))
                llm_calls_total.add(amount=1,attributes={"model":model,"status":"error"})
                raise

llm_tracer=LLMTracer(tracer)

@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ OpenTelemetry tracing active")
    yield

app=FastAPI(title="Traced Gen AI API ",lifespan=lifespan)

# Auto-instrument FastAPI — adds trace to every request automatically
FastAPIInstrumentor.instrument_app(app) # This ONE line automatically adds tracing to EVERY endpoint in your FastAPI app - without touching your route code!

app.add_middleware(TelemetryMiddleware)

# ============================================================
# SCHEMAS
# ============================================================
class GenerateRequest(BaseModel):
    prompt:str
    model:str="gpt-4"
    max_tokens:int=512

# ============================================================
# ROUTES
# ============================================================
@app.post("/api/v1/generate")
async def generate(req:GenerateRequest,request:Request):
    """
    LLM generation with full tracing.
    In Jaeger you'll see the complete breakdown:
    handle_request → auth → vector_search → llm_call
    """
    current_span=trace.get_current_span()
    current_span.set_attribute("user.model_requested",req.model)
    current_span.set_attribute("request.prompt_length",len(req.prompt))

    # Simulate full RAG + LLM pipeline with individual spans
    async def do_embed():
        with tracer.start_as_current_span(name="embed_query") as s:
            s.set_attribute("embedding_model","text-embedding-ada-002")
            await asyncio.sleep(0.1)
            s.set_attribute("embedding.dimensions",1536)
            return [0.1,0.2,0.3]
        
    async def do_search():
        with tracer.start_as_current_span(name="vector_search") as s:
            s.set_attribute("vector_db.provider","qdrant")
            s.set_attribute("vector_db.collections","documents")
            await asyncio.sleep(0.1)
            s.set_attribute("vector_db.results_found",5)
            return ["chunk1","chunk2"]
        
    # Parallel retrieval — both spans run concurrently
    embedding,chunks=await asyncio.gather(do_embed(),do_search())

    # Sequential LLM call — after retrieval
    async def llm_call():
        await asyncio.sleep(0.8)
        return {
            "response":f"Response to :{req.prompt[:30]}",
            "tokens_used":len(req.prompt.split())*10,
            "cost_used":0.0235
        }
    result=await llm_tracer.traced_call(
        model=req.model,
        prompt=req.prompt,
        call_fn=llm_call
    )

    current_span.set_attribute("response.tokens",result["tokens_used"])
    current_span.set_attribute("response.cost_used",result["cost_used"])

    return {
        **result,
        "trace_id":format(current_span.get_span_context().trace_id,"032x")
    }

@app.get("/api/v1/items")
async def get_items():
    with tracer.start_as_current_span(name="db.query_items") as span:
        span.set_attribute("db.system","postgresql")
        span.set_attribute("db.operation","SELECT")
        await asyncio.sleep(0.05)
        span.set_attribute("db.rows_returned",5)
    return {"items": [{"id":i,"name":f"item_{i}"} for i in range(5)]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint():
    """
    In production use prometheus-fastapi-instrumentator.
    This is a simplified metrics endpoint.
    """
    return {
        "service":    "genai-api",
        "version":    "1.0.0",
        "metrics_note": "In production: /metrics returns Prometheus format"
    }



     


    




