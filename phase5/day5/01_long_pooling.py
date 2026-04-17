import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Request
from collections import defaultdict,deque
import asyncio
import uuid
from datetime import datetime,timezone
from pydantic import BaseModel
from typing import Optional
from fastapi.responses import HTMLResponse

app=FastAPI(title="Long Pooling Demo")

# ============================================================
# EVENT QUEUE — stores pending events per client
# ============================================================
class EventQueue:
    def __init__(self):
        # client_id → queue of pending events [like collecting List of pending messages]
        self._queues:dict=defaultdict(lambda:deque(maxlen=100)) 
        # client_id → asyncio.Event (signals new data) [True when new message is waiting and false when client has collected the message]
        self._signals:dict={}

    def register_client(self,client_id:str):
        self._queues[client_id]=deque(maxlen=100)
        self._signals[client_id]=asyncio.Event()
        print(f"[LP] Client registered: {client_id}")

    def unregister_client(self,client_id:str):
        self._queues.pop(client_id,None)
        self._signals.pop(client_id,None)
        print(f"[LP] Client unregistered: {client_id}")

    # my_event = asyncio.Event()  # Create a doorbell

    # my_event.set()    # Change flag from False → True (RING!)
    # my_event.clear()  # Change flag from True → False (silent)
    # my_event.is_set() # Check if it's True or False
    # my_event.wait()   # Sleep until flag becomes True

    def push_event(self,client_id:str,event:dict):
        """Push event to a specific client"""
        if client_id in self._queues:
            self._queues[client_id].append(event)
            # Signal the waiting long poll request
            if client_id in self._signals:
                self._signals[client_id].set()
    
    def push_to_all(self,event:dict):
        """Broadcast event to all registered clients"""
        for client_id in list(self._queues.keys()):
            self.push_event(client_id=client_id,event=event)
    
    async def wait_for_events(self,client_id:str,timeout:float=30.0)->list:
        """
        Wait until events are available or timeout.
        This is the core of long polling.
        """
        if client_id not in self._queues:
            return []
        
        # If already have events — return immediately
        if self._queues[client_id]:
            events=list(self._queues[client_id])
            self._queues[client_id].clear()
            return events
        
        # No events — wait for signal or timeout
        signal=self._signals[client_id]
        signal.clear()

        try:
            await asyncio.wait_for(signal.wait(),timeout=timeout)
        except asyncio.TimeoutError:
            return [] # empty response — client will retry
        
        # Collect all pending events
        events=list(self._queues[client_id])
        self._queues[client_id].clear()
        return events
    
event_queues=EventQueue()


# ============================================================
# SCHEMAS
# ============================================================
class PushEventRequest(BaseModel):
    client_id:Optional[str]=None
    event_type:str
    data:dict={}

# ============================================================
# ROUTES
# ============================================================

@app.post("/lp/register")
def register_client():
    """Client calls this first to get a client_id"""
    client_id=str(uuid.uuid4())[:8]
    event_queues.register_client(client_id=client_id)
    print(f"Client registered : {event_queues._queues}")
    print(f"Events registered : {event_queues._signals}")
    return {
        "client_id":client_id,
        "message":"Registered! Now poll /lp/poll/{client_id}"
    }


@app.get("/lp/poll/{client_id}")
async def long_pool(client_id:str,request:Request,timeout:float=30.0):
    """
    The long poll endpoint.
    Client calls this and WAITS until events arrive or timeout.
    On timeout → client immediately calls again.
    """
    if client_id not in event_queues._signals:
        return {"error":"Unknown client. Call /lp/register first"}
    
    # Check if client disconnected while waiting
    async def check_disconnect():
        while True:
            if await request.is_disconnected():
                return True
            await asyncio.sleep(0.5)

    # Race: wait for events OR client disconnect
    event_tasks=asyncio.create_task(event_queues.wait_for_events(client_id=client_id,timeout=timeout))
    disconnect_tasks=asyncio.create_task(check_disconnect())

    done,pending=await asyncio.wait([event_tasks,disconnect_tasks],return_when=asyncio.FIRST_COMPLETED)
    print(f"DONE : {done}")
    print(f"PENDING : {pending}")
    # Cancel remaining tasks
    for task in pending:
        task.cancel()

    if disconnect_tasks in done:
        print(f"[LP] Client {client_id} disconnected")
        return {"events": [], "disconnected": True}
    
    events=event_tasks.result()
    print(f"EVENTS : {events}")
    return {
        "events":events,
        "count":len(events),
        "timestamp":datetime.now(timezone.utc).isoformat(),
        "next_poll":f"/lp/poll/{client_id}"
    }


@app.post("/lp/push")
async def push_event(req:PushEventRequest):
    """Push event to one client or broadcast to all"""
    event={
        "id":str(uuid.uuid4())[:8],
        "type":req.event_type,
        "data":req.data,
        "timestamp":datetime.now(timezone.utc).isoformat()
    }
    if req.client_id:
        event_queues.push_event(client_id=req.client_id,event=event)
        return {"pushed_to":req.client_id}
    else:
        event_queues.push_to_all(event=event)
        return {"broadcast_to":len(event_queues._queues)}
    
@app.delete("/lp/unregister/{client_id}")
def unregister(client_id:str):
    event_queues.unregister_client(client_id=client_id)
    return {"message":"Unregistered"}

# ============================================================
# REAL GEN AI USE CASE — poll for document processing status
# ============================================================
processing_jobs:dict={}

@app.post("/jobs/start")
async def start_job(document_name:str):
    """Start a background job and return job_id for polling"""
    job_id=str(uuid.uuid4())[:8]
    processing_jobs[job_id]={
        "status":"pending",
        "progress":0,
        "result":None,
        "created_at":datetime.now(timezone.utc).isoformat()
    }
    # Start background processing
    asyncio.create_task(simulate_document_processing(job_id,document_name))
    return {"job_id":job_id,"status":"pending"}

async def simulate_document_processing(job_id:str,doc_name:str):
    """Simulate RAG document processing pipeline"""
    steps=[
        ("parsing",20),
        ("chunking",40),
        ("embedding",70),
        ("storing",90),
        ("complete",100)
    ]
    for step,progress in steps:
        await asyncio.sleep(0.1)
        processing_jobs[job_id].update({"status":step,"progress":progress})
        print(f"[JOB {job_id}] {step}: {progress}%")
    processing_jobs[job_id]["result"]={"document":doc_name,"chunks":42,"token":8500}


@app.get("/jobs/{job_id}/status")
async def poll_job_status(job_id:str,request:Request):
    """
    Long poll for job status.
    Returns immediately if job is done.
    Waits up to 5s if job is still processing.
    """
    if job_id not in processing_jobs:
        return {"error":"Job not found"}
    
    job=processing_jobs[job_id]

    # Already complete — return immediately
    if job["status"]=="complete":
        return job
    
    # Still processing — wait up to 5s for update
    start=asyncio.get_event_loop().time()
    last_status=job["status"]

    while asyncio.get_event_loop().time()-start<5.0:
        if await request.is_disconnected():
            break
        current_job=processing_jobs[job_id]

        # Status changed — return update
        if current_job["status"]!=last_status:
            return current_job
        
        # Complete — return immediately
        if current_job["status"]=="complete":
            return current_job
        
        await asyncio.sleep(0.2)
    # Timeout — return current status, client polls again
    return processing_jobs[job_id]


# ============================================================
# BROWSER TEST PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Long Polling Test</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            .log { border: 1px solid #ccc; padding: 10px; height: 200px;
                   overflow-y: auto; font-family: monospace; font-size: 13px; }
            button { padding: 8px 16px; margin: 4px; cursor: pointer; }
            input  { padding: 8px; width: 200px; }
            .event   { color: #2196F3; }
            .system  { color: #FF9800; }
            .job     { color: #4CAF50; }
        </style>
    </head>
    <body>
        <h2>⏳ Long Polling Demo</h2>

        <h3>Event Polling</h3>
        <button onclick="startPolling()">Start Polling</button>
        <button onclick="stopPolling()">Stop</button>
        <br>
        <input id="eventType" value="notification" placeholder="Event type"/>
        <input id="eventData" value="Hello!" placeholder="Event data"/>
        <button onclick="pushEvent()">Push Event</button>
        <div id="eventLog" class="log"></div>

        <h3>Job Status Polling</h3>
        <input id="docName" value="my_document.pdf" placeholder="Document name"/>
        <button onclick="startJob()">Start Processing Job</button>
        <div id="jobLog" class="log"></div>

        <script>
            let clientId = null;
            let polling  = false;
            const eventLog = document.getElementById('eventLog');
            const jobLog   = document.getElementById('jobLog');

            function log(el, msg, type = 'system') {
                const div = document.createElement('div');
                div.className = type;
                div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
                el.appendChild(div);
                el.scrollTop = el.scrollHeight;
            }

            async function startPolling() {
                // Register client
                const res = await fetch('/lp/register', { method: 'POST' });
                const data = await res.json();
                clientId = data.client_id;
                polling = true;
                log(eventLog, `Registered as: ${clientId}`, 'system');
                poll();
            }

            async function poll() {
                while (polling && clientId) {
                    try {
                        log(eventLog, 'Waiting for events...', 'system');
                        const res = await fetch(`/lp/poll/${clientId}?timeout=10`);
                        const data = await res.json();

                        if (data.events?.length > 0) {
                            data.events.forEach(e => {
                                log(eventLog, `Event: ${e.type} → ${JSON.stringify(e.data)}`, 'event');
                            });
                        }
                    } catch(e) {
                        log(eventLog, `Error: ${e.message}`, 'system');
                        await new Promise(r => setTimeout(r, 2000));
                    }
                }
            }

            async function pushEvent() {
                await fetch('/lp/push', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        client_id: clientId,
                        event_type: document.getElementById('eventType').value,
                        data: { message: document.getElementById('eventData').value }
                    })
                });
            }

            function stopPolling() {
                polling = false;
                if (clientId) {
                    fetch(`/lp/unregister/${clientId}`, { method: 'DELETE' });
                    clientId = null;
                }
                log(eventLog, 'Polling stopped', 'system');
            }

            async function startJob() {
                const docName = document.getElementById('docName').value;
                log(jobLog, `Starting job for: ${docName}`, 'system');

                const res  = await fetch(`/jobs/start?document_name=${docName}`, { method: 'POST' });
                const data = await res.json();
                const jobId = data.job_id;
                log(jobLog, `Job started: ${jobId}`, 'system');

                // Poll until complete
                let lastStatus = '';
                while (true) {
                    const r = await fetch(`/jobs/${jobId}/status`);
                    const job = await r.json();

                    if (job.status !== lastStatus) {
                        log(jobLog, `[${jobId}] ${job.status} (${job.progress}%)`, 'job');
                        lastStatus = job.status;
                    }

                    if (job.status === 'complete') {
                        log(jobLog, `Done! ${JSON.stringify(job.result)}`, 'job');
                        break;
                    }
                }
            }
        </script>
    </body>
    </html>
    """
        