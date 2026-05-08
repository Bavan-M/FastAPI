import os,sys
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
import time
from typing import Optional
from celery import Celery,chain,chord,group
from kombu import Queue,Exchange
from celery.utils.log import get_logger



# ============================================================
# CELERY APP SETUP
# ============================================================
"""
Celery needs:
  broker  → where tasks are sent (RabbitMQ or Redis)
  backend → where results are stored (Redis, DB, or RabbitMQ)

broker  = the post office
backend = the filing cabinet for results
"""
celery_app=Celery(main="it_ops_tasks",
                  broker=os.getenv("CELERY_BACKEND","amqp://admin:admin123@localhost:5672//"),
                  backend=os.getenv("CELERY_BROKER","redis://localhost:6379/0"))
# Redis has 16 databases (numbered 0 to 15) that act like separate compartments in the same storage system.
# redis://localhost:6379/0  → Only Celery results
# redis://localhost:6379/1  → Only cache
# redis://localhost:6379/2  → Only sessions
# redis://localhost:6379/3  → Only rate limiting

# Beautiful organization! 🎉


# ============================================================
# CELERY CONFIGURATION
# ============================================================
celery_app.conf.update(
    task_serializer="json", #Write all orders in English
    result_serializer="json",
    accept_content=["json"],

    result_expires=3600, # Keep records for 1 hour only
    task_track_started=True, # Show 'Chef started cooking' status
    task_acks_late=True, # Say 'Done' ONLY after pizza is made
    worker_prefetch_multiplier=1, # Chefs take 1 order at a time

    task_max_retires=3, # Try failed orders 3 times
    task_defualt_retry_delay=60, # Wait 60 seconds between tries

    task_queus=( # Different counters for different tasks, critical gets priority
        Queue(name="critical",exchange=Exchange(name="critical"),routing_key="critical",queue_arguments={"x-max-priority":10}),
        Queue(name="default",exchange=Exchange(name="default"),routing_key="default"),
        Queue(name="llm",exchange=Exchange(name="llm"),routing_key="llm"),
        Queue(name="ingestion",exchange=Exchange(name="ingestion"),routing_key="ingestion"),
        Queue(name="low",exchange=Exchange(name="low"),routing_key="low")
    ),
    task_default_queue="default",
    task_default_exchange="defualt",

    worker_send_task_events=True, #Security cameras everywhere
    task_send_sent_events=True,

    beat_schedule={ # Robots do recurring jobs automatically
        "cleanup_old_results":{
            "task":"phase8.day2.02_celery_basics.cleanup_old_results",
            "schedule":3600
        },
        "health_check_services":{
            "task":"phase8.day2.02_celery_basics.check_service_health",
            "schedule":60
        }
    }
)

logger=get_logger(__name__)

# ============================================================
# TASKS — the heart of Celery
# ============================================================

@celery_app.task(
    name="process_document", # This job is called 'Process Documen
    queue="ingestion",  # Go to the INGESTION counte Queue
    bind=True, # Chef knows his own order number
    max_retires=3, # Try 3 times before giving up
    default_retry_delay=30, # Wait 30 seconds before retry
    acks_late=True # Say 'Done' ONLY after pizza is made
)
def process_document(self,doc_id:int,filename:str,content:str):
    """
    Process a document through the RAG ingestion pipeline.
    Runs in a Celery worker — not in the FastAPI process.

    bind=True lets us:
    - Access self.retry() for retry logic
    - Access self.request.id for task ID
    - Update task state during long operations
    """
    logger.info(msg=f"Processing document {doc_id} ({filename})")

    try:
        self.update_state(state="PROGRESS",meta={"step":"parsing","progress":10})
        time.sleep(10)

        self.update_state(state="PROGRESS",meta={"step":"chunking","progress":40})
        time.sleep(10)

        self.update_state(state="PROGRESS",meta={"step":"embedding","progress":70})
        time.sleep(10)

        self.update_state(state="PROGRESS",meta={"step":"storing","progress":100})
        time.sleep(10)

        result={
            "doc_id":doc_id,
            "filename":filename,
            "chunks":42,
            "tokens":8500,
            "status":"ready",
            "processed_at":time.time()
        }

        logger.info(f"Document {doc_id} processed successfully: {result['chunks']} chunks")

        return result
    except Exception as e:
        logger.error(f"Document processing failed for {doc_id}: {e}")
        raise self.retry(exc=e,countdown=30 * (2 ** self.request.retries))

# ┌─────────────────────────────────────────────────────────────┐
# │  FASTAPI (Web Server)                                       │
# │                                                             │
# │  # User uploads document                                    │
# │  result = process_document.delay(                           │
# │      doc_id="123",                                          │
# │      filename="contract.pdf",                               │
# │      content="PDF content..."                               │
# │  )                                                          │
# │  print(result.id)  # "abc-123-def"                          │
# └─────────────────────┬───────────────────────────────────────┘
#                       │
#                       │ Task goes to RabbitMQ
#                       ▼
# ┌─────────────────────────────────────────────────────────────┐
# │  RABBITMQ (Broker)                                          │
# │                                                             │
# │  Queue: "ingestion"                                         │
# │  [📋 Task: process_document, args: doc_id="123"...]        │
# └─────────────────────┬───────────────────────────────────────┘
#                       │
#                       │ Worker picks up
#                       ▼
# ┌─────────────────────────────────────────────────────────────┐
# │  CELERY WORKER (Chef)                                       │
# │                                                             │
# │  def process_document(self, doc_id, filename, content):     │
# │      try:                                                   │
# │          # Step 1: Parsing (10%)                            │
# │          self.update_state(meta={"progress": 10})           │
# │                                                             │
# │          # Step 2: Chunking (40%)                           │
# │          self.update_state(meta={"progress": 40})           │
# │                                                             │
# │          # Step 3: Embedding (70%)                          │
# │          self.update_state(meta={"progress": 70})           │
# │                                                             │
# │          # Step 4: Storing (90%)                            │
# │          self.update_state(meta={"progress": 90})           │
# │                                                             │
# │          return result  # SUCCESS ✅                       │
# │                                                            │
# │      except Exception as exc:                               │
# │          # Retry with exponential backoff                   │
# │          raise self.retry(countdown=30 * (2 ** retries))    │
# └─────────────────────┬───────────────────────────────────────┘
#                       │
#                       │ Store result
#                       ▼
# ┌────────────────────────────────────────────────────────────┐
# │  REDIS (Backend)                                           │
# │                                                            │
# │  task_id: "abc-123-def" → {                                │
# │      "status": "SUCCESS",                                  │
# │      "result": {                                           │
# │          "doc_id": "123",                                  │
# │          "chunks": 42,                                     │
# │          "status": "ready"                                 │
# │      }                                                     │
# │  }                                                         │
# └────────────────────────────────────────────────────────────┘
#                       │
#                       │ FastAPI can check result
#                       ▼
# ┌─────────────────────────────────────────────────────────────┐
# │  FASTAPI (Web Server) - Later                               │
# │                                                             │
# │  # Check if task is done                                    │
# │  result = AsyncResult("abc-123-def", app=celery_app)        │
# │  if result.ready():                                         │
# │      print(result.result)  # {"chunks": 42, ...}            │
# └─────────────────────────────────────────────────────────────┘


@celery_app.task(
    name="call_llm",
    queue="llm",
    bind=True,
    max_retires=3,
    soft_time_limit=60, # "Chef, please wrap it up!" (gentle warning
    time_limit=90 #   "I'm shutting down the oven NOW!" (force kill)
)
def call_llm_task(self,prompt:str,model:str="gpt-4",user_id:int=None):
    """
    LLM call as a Celery task.
    Use when you want async LLM processing — fire and check result later.
    """
    logger.info(f"LLM task started: model={model}, user={user_id}")
    try:
        time.sleep(2)
        result = {
            "response":    f"[{model}] Response to: {prompt[:30]}",
            "tokens_used": len(prompt.split()) * 10,
            "cost_usd":    0.0235,
            "model":       model,
            "user_id":     user_id
        }
        logger.info(f"LLM task complete: {result['tokens_used']} tokens")
        return result
    except Exception as e:
        if "rate_limit" in str(e).lower():
            raise self.retry(exc=e, countdown=60)
        raise self.retry(exc=e, countdown=10)

@celery_app.task(
    name="send_notification",
    queue="default",
    max_retries=5,
    default_retry_delay=5
)
def send_notification(user_email:str,subject:str,body:str,channel:str = "email"):
    """
    Send notification via email/Slack/Teams.
    Always runs async — never block user for notifications.
    """
    logger.info(f"Sending {channel} to {user_email}: {subject}")
    time.sleep(0.5)   # simulate sending
    return {"sent": True, "channel": channel, "recipient": user_email}

@celery_app.task(
    name="create_incident_report",
    queue="default"
)
def create_incident_report(incident_id: str, severity: str):
    """
    Generate AI-powered incident report.
    Chains multiple tasks: gather data → generate report → notify
    """
    logger.info(f"Creating report for incident {incident_id}")
    time.sleep(1)
    return {
        "incident_id": incident_id,
        "report":      f"Incident {incident_id} report generated",
        "severity":    severity
    }

@celery_app.task(name="cleanup_old_results", queue="low")
def cleanup_old_results():
    """Periodic maintenance task — run by Celery Beat"""
    logger.info("Cleaning up old results...")
    time.sleep(0.5)
    return {"cleaned": True, "timestamp": time.time()}


@celery_app.task(name="check_service_health", queue="default")
def check_service_health():
    """Periodic health check — run by Celery Beat"""
    logger.info("Checking service health...")
    return {"healthy": True, "checked_at": time.time()}


# ============================================================
# TASK CHAINS, GROUPS, CHORDS
# ============================================================

"""
Celery has three powerful composition primitives:

CHAIN: tasks run sequentially, output of one is input of next
  chain(task1, task2, task3)
  task1 result → task2 input → task3 input → final result

GROUP: tasks run in parallel, collect all results
  group(task1, task2, task3)
  All run simultaneously → list of results

CHORD: group + callback — parallel tasks then one final task
  chord(group(task1, task2, task3), callback)
  All run in parallel → callback gets all results
"""


def demo_task_composition():
    # CHAIN: process doc → notify user
    # Result of process_document feeds into send_notification
    # Use .s() (Mutable) When=> Next task NEEDS previous result
    # Use .si() (Immutable) When => Next task has its own fixed arguments
    doc_pipeline=chain(
        process_document.si("doc_123","report.pdf","content here"),
        send_notification.si("user@gmail.com","Document processed","Your document is ready")
    )

    # GROUP: process multiple documents in parallel
    parallel_docs=group(
        process_document.si(f"doc_{i}",f"file_{i}.pdf",f"Content...{i}")
        for i in range(5)
    )

    # CHORD: process all docs in parallel, then send summary
    # Callback receives list of all group results
    doc_batch=chord(
        group(
            process_document.si(f"doc_{i}",f"file_{i}.pdf",f"Content...{i}")
        for i in range(3)
        ),
        send_notification.si("admin@gmail.com","Batch complete","All 3 documents processes")
    )

    print("Task composition examples defined (not running — no workers)")
    print("To run: doc_pipeline.delay() or doc_pipeline.apply_async()")

    return doc_pipeline,parallel_docs,doc_batch

if __name__ == '__main__':
    # This only runs when you execute the file directly, not when Celery imports it
    doc_pipeline, parallel_docs, doc_batch = demo_task_composition()

