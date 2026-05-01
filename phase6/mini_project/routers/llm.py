import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from models.schemas import GenerateRequest, GenerateResponse
from routers.auth import get_current_user
from core.config import settings
from core.logging import llm_logger
from core.resilience import with_timeout, retry

router = APIRouter(prefix="/llm", tags=["LLM"])
tracer = trace.get_tracer("genai-api")

async def simulate_llm_call(prompt:str,model:str)->dict:
    """
    Simulated LLM call.
    Replace with:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    """
    await asyncio.sleep(0.5)
    return {
        "response":    f"[{model}] Response to: {prompt[:40]}",
        "tokens_used": len(prompt.split()) * 10,
        "cost_usd":    len(prompt.split()) * 10 * 0.00003
    }

@router.post("/generate",response_model=GenerateResponse)
async def generate(req:GenerateRequest,request:Request,current_user:dict=Depends(get_current_user)):
    request_id=getattr(request.state,"request_id","unknown")
    current_span=trace.get_current_span()
    current_span.set_attribute("user.id",current_user["id"])
    current_span.set_attribute("llm.model",req.model)
    current_span.set_attribute("llm.prompt_length",   len(req.prompt))

    llm_logger.bind(
        request_id=request_id,
        user=      current_user["username"],
        model=     req.model
    ).info("LLM generation started")

    start=time.perf_counter()
    try:
        result=await with_timeout(
            coro=retry(
                        coro_factory=lambda : simulate_llm_call(req.prompt,req.model),
                        max_attempt=settings.llm_timeout>0 and 3 or 1,
                        operation="llm_call"),
            timeout=settings.llm_timeout,
            operation="LLM generation"
        )
        latency=(time.perf_counter()-start)*1000

        current_span.set_attribute("llm.tokens_used", result["tokens_used"])
        current_span.set_attribute("llm.cost_usd",    result["cost_usd"])
        current_span.set_status(StatusCode.OK)

        llm_logger.bind(
            request_id= request_id,
            model=      req.model,
            tokens=     result["tokens_used"],
            cost_usd=   result["cost_usd"],
            latency_ms= round(latency)
        ).success("LLM generation complete")

        return {
            **result,
            "model": req.model,
            "prompt":     req.prompt,
            "latency_ms": round(latency, 2),
            "request_id": request_id,
            "trace_id":   format(
                current_span.get_span_context().trace_id, "032x"
            )
        }
    except Exception as e:
        llm_logger.bind(
            request_id=request_id,
            error=str(e)
        ).error("LLM generation failed")
        raise

@router.get("/status")
async def llm_status():
    return {
        "available":     True,
        "default_model": settings.default_model,
        "timeout":       settings.llm_timeout,
        "openai":        bool(settings.openai_api_key),
        "anthropic":     bool(settings.anthropic_api_key)
    }





