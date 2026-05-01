import os,sys
sys.path.insert(0,os.path.dirname(__file__))

import time
import asyncio
from opentelemetry import trace,metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter,SimpleSpanProcessor
from opentelemetry.trace import StatusCode
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter,PeriodicExportingMetricReader


def setup_tracer(service_name:str="genai-api")->trace.Tracer:
    """
    Configure OpenTelemetry tracer.
    In production export to Jaeger, Zipkin, or Grafana Tempo.
    Here we print to console so you can see what's happening.
    """
    # Resource describes your service
    resource=Resource(
        {
            "service.name":service_name, # Detective's name badge
            "service.version":"1.0.0", # Which training batch they're from
            "deployement.environment":"development" # Rookie detectives, not veterans yet
        }
    )

    # Provider manages tracers
    provider=TracerProvider(resource=resource) # Opening the main detective headquarters (central command)

    # Exporter sends spans somewhere
    # ConsoleSpanExporter → prints to terminal (dev only)
    exporter=ConsoleSpanExporter() # Installing a CCTV monitor in your office (watch everything live)

    # Processor batches spans before exporting
    processor=SimpleSpanProcessor(span_exporter=exporter) # Hiring a clerk to organize messy case notes
    provider.add_span_processor(span_processor=processor) # Telling headquarters: "This clerk works for us now"

    # Register as global provider
    trace.set_tracer_provider(tracer_provider=provider) # Putting the rulebook in every department (everyone use THIS system)

    # Return a tracer for this module
    return trace.get_tracer(service_name) # Handing out detective kits (notebook + stopwatch) to each investigator

tracer=setup_tracer("genai-api") # Opening the GenAI API detective agency


def demo_basic_span():
    print("\n=== Basic Spans ===")                              # "New case day at detective agency"

    # start_as_current_span creates a span and sets it as current
    # Everything inside the with block is part of this span
    # # Lead detective opens notebook name called handle_user_request and starts case timer
    with tracer.start_as_current_span(name="handle_user_request") as span:
        # Add attributes — searchable metadata about this span
        # By adding these atributes it will be easy for us to search a particular span(case)
        span.set_attribute(key="user.id",value="user_123") # Detective writes: "Client is user_123" on case file
        span.set_attribute(key="request.path",value="/api/v1/generate") # Detective writes: "Requested path is /api/v1/generate"
        span.set_attribute(key="request.method",value="POST") # Detective writes: "Method used is POST"

        print("Processing request...") # Detective mutters: "Alright, let's work on this case"
        time.sleep(0.1) # Detective spends 0.1 seconds on initial processing

        # Child span — nested inside parent
        # Junior detective: "Let me check if client has permission"
        with tracer.start_as_current_span(name="verify_auth") as auth_span:
            auth_span.set_attribute("auth.method","jwt") # Junior detective notes: "Using JWT authentication method"
            time.sleep(0.02) # Junior detective spends 0.02 seconds verifying credentials
            auth_span.set_status(StatusCode.OK) # Junior detective stamps: "VERIFIED - authorized"
            print("Auth verified")  # Junior detective shouts: "Permission granted!"

        # Another child span
        # Database specialist: "I'll fetch user data"
        with tracer.start_as_current_span(name="db_query") as db_span:
            db_span.set_attribute("db.system","postgresql") # Database specialist notes: "Using PostgreSQL database"
            db_span.set_attribute("db.statement","SELECT * FROM users WHERE id=$1") # Database specialist writes exact SQL query
            time.sleep(0.03) # Database specialist searches for 0.05 seconds
            db_span.set_attribute("db.rows_returned",1) # Database specialist notes: "Found 1 user record"
            print("DB query done")  # Database specialist says: "Data fetched successfully"
            
        span.set_status(StatusCode.OK) # Lead detective stamps final: "CASE SOLVED - OK"
        span.set_attribute("response.status_code",200) # Lead detective writes: "Returned HTTP 200 success"
        print("Request handled")   # Lead detective closes notebook: "Case complete!"


# ============================================================
# SPANS WITH EVENTS — record notable moments
# To know what is happeneing at the moment we use add_event
# To know what is the value or facts during the call we use set_attribute
# ============================================================
def demo_span_events():
    print("\n=== Span Events ===")

    with tracer.start_as_current_span(name="llm_generation") as span:
        span.set_attribute("llm.model","gpt-4")
        span.set_attribute("llm.prompt_length",150)

        # Events are timestamped log entries inside a span
        span.add_event(name="generation_started",
                       attributes={
                           "prompt_tokens":150,
                           "max_tokens":512
                       })
        time.sleep(0.5) # simulate LLM call                   # AI is thinking... (0.5 seconds pass)
        span.add_event(name="first_token_recieved",
                       attributes={
                           "time_to_first_token_ms":450
                       })
        time.sleep(0.3)
        span.add_event(name="generation_complete",
                       attributes={
                           "completion_tokens":320,
                           "total_tokens":470,
                           "cost_usd":0.023
                       })
        span.set_attribute("llm.completion_tokens",320)
        span.set_attribute("llm.total_tokens",470)
        span.set_attribute("llm.cost_usd",0.0273)
        span.set_status(StatusCode.OK)

# ============================================================
# ERROR RECORDING IN SPANS
# ============================================================
def demo_error_spans():
    print("\n=== Error Spans ===")

    with tracer.start_as_current_span(name="call_external_api") as span:
        span.set_attribute("http.url","https://api.openai.com/v1/chat/completions")
        try:
            raise ConnectionError("Openai API timeout after 10s")
        except Exception as e:
            span.record_exception(exception=e)
            span.set_status(StatusCode.ERROR,description=str(e))
            span.set_attribute("error.type",type(e).__name__)
            span.set_attribute("error.message",str(e))
            print(f"Error recorded in span: {e}")


# ============================================================
# ASYNC SPANS
# ============================================================
async def demo_async_spans():
     print("\n=== Async Spans ===") # "New day at detective agency - big complex case!"

     with tracer.start_as_current_span(name="async_rag_pipeline") as span:
        span.set_attribute("rag.query","What is Langgraph?")
        
        # Parallel async operations — each gets its own span
        async def embed_query(): # Detective A's task: Convert question to numbers
            with tracer.start_as_current_span(name="embed_query") as s:
                s.set_attribute("embedding.model","text-embedding-ada-002")
                await asyncio.sleep(0.1)
                s.set_attribute("embedding.dimension",1536)

        async def vector_search():
            with tracer.start_as_current_span(name="vector_search") as s:
                s.set_attribute("vector_db.collection", "documents")
                s.set_attribute("vector_db.top_k", 5)
                await asyncio.sleep(0.3)
                s.set_attribute("vector_db.results", 5)
        
        async def fetch_user_context():
            with tracer.start_as_current_span("fetch_user_context") as s:
                s.set_attribute("db.table", "users")
                await asyncio.sleep(0.05)

        # Run all in parallel — spans run concurrently
        await asyncio.gather(
            embed_query(),
            vector_search(),
            fetch_user_context()
        )

        # LLM call after retrieval
        with tracer.start_as_current_span("llm_call") as llm_span:
            llm_span.set_attribute("llm.model", "gpt-4")
            await asyncio.sleep(0.5)
            llm_span.set_attribute("llm.tokens", 450)

        span.set_status(StatusCode.OK)
        print("RAG pipeline complete")

def setup_metrics():
    """Configure metrics collection"""
    exporter=ConsoleMetricExporter() # Install a "Report Printer" that prints numbers to CCTV monitor
    reader=PeriodicExportingMetricReader(exporter=exporter,export_interval_millis=5000) # Create a "Data Collector" that automatically gathers stats EVERY 5 SECONDS and sends to printer
    provider=MeterProvider(metric_readers=[reader]) # Build central "Statistics Hub" holding all dashboards
    metrics.set_meter_provider(meter_provider=provider) # Register hub as OFFICIAL agency dashboard system
    return metrics.get_meter(name="genai-api") # Hand agency a new "Stats Counter" named "genai-api" to start counting!

meter=setup_metrics()

# Define metrics instruments
request_counter=meter.create_counter(name="api.request.total",unit="request",description="Total API Request")
llm_cost_histogram=meter.create_histogram(name="llm.cost.used",unit="usd",description="Cost per LLM call in USD")
active_connections=meter.create_up_down_counter(name="api.active.connections",description="Currently active Websocket Connections")
llm_latency=meter.create_histogram(name="llm.latency.used",unit="ms",description="LLM call latency in milliseconds")


def demo_metrics():
    print("\n=== Metrics ===")

    # Record a request
    request_counter.add(amount=1,
                        attributes={
                            "method":"POST",
                            "path":"/api/v1/generate",
                            "status_code":"200",
                            "model":"gpt-4"
                        })
    
    # Record LLM cost
    llm_cost_histogram.record(amount=0.0245,
                              attributes={
                                  "model":"gpt-4",
                                  "project_id":"project_4"
                              })
    # Record latency
    llm_latency.record(amount=2300,attributes={"model":"gpt-4"})
    llm_latency.record(amount=1800,attributes={"model":"gpt-3.5-turbo"})

    # WebSocket connections
    active_connections.add(amount=1) # user connected
    active_connections.add(amount=1) # another user
    active_connections.add(amount=-1) # user disconnected

    print("Metrics recorded — check console output after 5s")



         

if __name__=="__main__":
    demo_basic_span()
    demo_span_events()
    demo_error_spans()
    asyncio.run(demo_async_spans())
    demo_metrics()
    time.sleep(6)







 


