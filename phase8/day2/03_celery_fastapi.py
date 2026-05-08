import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from package_02_celery_basics import celery_app,process_document,call_llm_task,send_notification,create_incident_report

from pydantic import BaseModel
from typing import Optional
from celery.result import AsyncResult
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
import uuid


# ============================================================
# SCHEMAS
# ============================================================

class TaskResponse(BaseModel):
    task_id:str
    status:str
    message:str
    poll_url:str

class TaskStatusResponse(BaseModel):
    task_id:str
    status:str # PENDING, STARTED, PROGRESS, SUCCESS, FAILURE
    progress:Optional[int]=None
    result:Optional[dict]=None
    error:Optional[str]=None

class GenerateRequest(BaseModel):
    prompt:str
    model:str="gpt-4"
    async_mode:bool=True # True = Celery task, False = wait for result



# ============================================================
# TASK STATUS HELPER
# ============================================================
def get_task_status(task_id:str)->TaskStatusResponse:
    """
    Get current status of a Celery task.
    Celery stores state in Redis backend.
    """
    result=AsyncResult(id=task_id,app=celery_app)

    if result.state=="PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            status="pending",
            message="Task is queued , waiting for the worker"
        )
    elif result.state=="STARTED":
        return TaskStatusResponse(
            task_id=task_id,
            status="started",
            message="Worker has picked up the task"
        )
    elif result.state=="PROGRESS":
        meta=result.info or {}
        return TaskStatusResponse(
            task_id=task_id,
            status="processing",
            progress=meta.get("progress",0),
            message=f"Step: {meta.get('step', 'processing')}"
        )
    elif result.state=="SUCCESS":
        return TaskStatusResponse(
            task_id=task_id,
            status="success",
            progress=100,
            result=result.result
        )
    elif result.state=="FAILURE":
        return TaskStatusResponse(
            task_id=task_id,
            status="failed",
            error=str(result.result)
        )
    elif result.state=="RETRY":
        return TaskStatusResponse(
            task_id=task_id,
            status="retry",
            message="Task failed, will retry shortly"
        )
    return TaskStatusResponse(
        task_id=task_id,
        status=result.state.lower()
    )


# ============================================================
# APP
# ============================================================
@asynccontextmanager
async def lifespan(app:FastAPI):
    print("✅ FastAPI + Celery integration ready")
    print("   Make sure RabbitMQ and Redis are running")
    print("   Start worker: celery -A phase8.day2.02_celery_basics worker -l info")
    yield

app=FastAPI(title="Fastapi + Celery Demo",lifespan=lifespan)

# ============================================================
# DOCUMENT INGESTION — fire and forget
# ============================================================
@app.post("/documents/upload",response_model=TaskResponse)
async def upload_document(filename:str,content:str):
    """
    Upload a document for RAG ingestion.
    Returns immediately with task_id — processing happens in background.
    """
    doc_id=f"doc_{uuid.uuid4().hex[:8]}" # get first 8 characters from 32 characters without hyphen 

    # Dispatch to Celery worker — non-blocking
    task=process_document.apply_async(
        args=[doc_id,filename,content],
        queue="ingestion",
        task_id=str(uuid.uuid4())
    )

    print(f"[FastAPI] Document {doc_id} queued for processing: {task.id}")

    return TaskResponse(
        task_id=task.id,
        status="queue",
        message="Document queued for processing. Use poll_url to check progress.",
        poll_url=f"/tasks/{task.id}"
    )

@app.get("/documents/{doc_id}/status")
async def document_status(doc_id:str,task_id:str):
    """Check processing status of a specific document"""
    return get_task_status(task_id=task_id)



# ============================================================
# LLM GENERATION — sync or async
# ============================================================

@app.post("/llm/generate")
async def generate(req:GenerateRequest):
    """
    Generate LLM response.
    async_mode=True  → Celery task, returns task_id immediately
    async_mode=False → wait for result (max 30s)
    """
    if req.async_mode:
        # Fire and forget — client polls for result
        task=call_llm_task.apply_async(
            args=[req.prompt,req.model],
            queue="llm"
        )
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message="LLM generation queued",
            poll_url=f"/task/{task.id}"
        )
    else:
        # Fire and forget — client polls for result
        task=call_llm_task.apply_async(
            args=[req.prompt,req.model],
            queue="llm"
        )
        try:
            # Wait up to 30 seconds
            result=task.get(timeout=30)
            return {"status":"success",**result}
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"LLM task failed {e}"
            )
        
