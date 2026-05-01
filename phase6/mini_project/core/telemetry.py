import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import StatusCode


def setup_telemetry(service_name: str, environment: str = "development"):
    resource = Resource.create({
        "service.name":           service_name,
        "service.version":        os.getenv("VERSION", "1.0.0"),
        "deployment.environment": environment
    })

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter())
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=30000
            )
        ]
    )
    metrics.set_meter_provider(meter_provider)

    tracer = trace.get_tracer(service_name)
    meter  = metrics.get_meter(service_name)

    # Instruments
    instruments = {
        "requests_total":  meter.create_counter(
            "http_requests_total",
            description="Total HTTP requests"
        ),
        "request_duration": meter.create_histogram(
            "http_request_duration_ms",
            description="HTTP request duration",
            unit="ms"
        ),
        "llm_calls":       meter.create_counter(
            "llm_calls_total",
            description="Total LLM calls"
        ),
        "llm_tokens":      meter.create_histogram(
            "llm_tokens_total",
            description="Tokens per LLM call"
        ),
        "llm_cost":        meter.create_histogram(
            "llm_cost_usd",
            description="LLM cost in USD",
            unit="usd"
        ),
        "active_requests": meter.create_up_down_counter(
            "active_requests",
            description="Active requests"
        )
    }

    return tracer, meter, instruments