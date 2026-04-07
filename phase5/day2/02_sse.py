import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse,HTMLResponse
from typing import AsyncGenerator
import time
import asyncio
import json

app=FastAPI(title="Server Sent Events Demo")

# SSE FORMAT
# SSE messages have a specific format:
# data: your message here\n\n         ← simple message
# event: custom_event\n               ← named event
# data: your message here\n\n
# id: 123\n                           ← message ID for resuming
# data: your message here\n\n
# retry: 3000\n                       ← reconnect after 3s

def sse_message(data:str, event:str=None, id:str=None)->str:
    message=""
    if id:
        message += f"id: {id}\n"      # ✅ Lowercase "id", colon, space
    if event:
        message += f"event: {event}\n" # ✅ Lowercase "event", colon, space
    message += f"data: {data}\n\n"     # ✅ Lowercase "data", colon, space
    return message

def sse_json(data:dict,event:str=None,id:str=None)->str:
    """SEE message with JSON format"""
    return sse_message(json.dumps(data),event,id)

# BASIC SSE
async def basic_sse_generator()->AsyncGenerator[str,None]:
    for i in range(5):
        yield sse_message(f"Message {i} at {time.time():.2f}")
        await asyncio.sleep(0.5)
    yield sse_message("[DONE]",event="completed")

@app.get("/sse/basic")
async def sse_basic():
    return StreamingResponse(
        basic_sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",      # Don't cache old data
            "Connection": "keep-alive",       # Keep connection open
            "X-Accel-Buffering": "no"         # Proxy: send immediately
        }
    )


# NAMED EVENTS — different event types
async def named_event_generator() -> AsyncGenerator[str, None]:
    # ✅ Fixed: lowercase field names and event names
    yield sse_json({"status": "initializing"}, event="system")  # ✅ lowercase
    await asyncio.sleep(0.5)

    for i in range(1, 6):
        yield sse_json(
            data={"progress": i * 20, "step": f"Processing step {i}"},  # ✅ lowercase
            event="progress",  # ✅ lowercase
            id=str(i)
        )
        await asyncio.sleep(0.5)

    tokens = "Here is the generated response token by token".split()
    for token in tokens:
        yield sse_json(
            data={"token": token},  # ✅ lowercase
            event="token"  # ✅ lowercase
        )
        await asyncio.sleep(0.1)

    yield sse_json(
        data={"message": "Generation complete", "total_tokens": len(tokens)},
        event="complete"  # ✅ lowercase
    )
@app.get("/sse/named-events")
async def sse_named_events():
    return StreamingResponse(
        named_event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

# SSE WITH CLIENT DISCONNECT DETECTION
# Without disconnect detection (Problem):
# python
# # User opens browser tab to see AI streaming
# User: "Show me 20 AI tokens"
# Browser: "Streaming started..."

# [After 5 seconds, user closes tab]
# User: [Gone, closed browser]

# But your server keeps generating:
# Token 6, Token 7, Token 8... 
# Token 15, Token 16...
# All the way to Token 20!

# WASTE: 15 tokens generated for nobody!
# With disconnect detection (Your solution):
# python
# # User opens browser tab
# User: "Show me 20 AI tokens"
# Browser: "Streaming started..."

# [After 5 seconds, user closes tab]
# Server checks: "Is client still connected?"
# Server: "Nope! They're gone"
# Server: [STOPS generating immediately]

# SAVED: No wasted tokens or processing!

async def sse_with_disconnect(request: Request) -> AsyncGenerator[str, None]:
    """
    Stop generating when client disconnects.
    Critical for LLM streaming — no point generating
    if the user closed the browser tab.
    """
    print("[SSE] Client connected")
    try:
        for i in range(20):
            # Check if client disconnected
            if await request.is_disconnected():
                print("[SSE] Client disconnected — stopping generation")
                break

            yield sse_json({"chunk": i, "text": f"Token {i} "}, event="token")
            await asyncio.sleep(0.3)

        yield sse_message("[DONE]", event="complete")

    except asyncio.CancelledError:
        print("[SSE] Stream cancelled")
    finally:
        print("[SSE] Cleanup done")

@app.get("/sse/with-disconnect")
async def sse_disconnect_aware(request:Request):
    return StreamingResponse(
        sse_with_disconnect(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# BROWSER TEST PAGE
@app.get("/test", response_class=HTMLResponse)
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>SSE Test</title></head>
    <body>
        <h2>SSE Test Page</h2>

        <button onclick="testBasic()">Test Basic SSE</button>
        <button onclick="testNamedEvents()">Test Named Events</button>
        <button onclick="stopStream()">Stop Stream</button>

        <div id="output" style="
            margin-top: 20px;
            padding: 10px;
            border: 1px solid #ccc;
            min-height: 200px;
            font-family: monospace;
            white-space: pre-wrap;
        "></div>

        <script>
            let eventSource = null;
            const output = document.getElementById('output');

            function log(msg, color = 'black') {
                output.innerHTML += `<span style="color:${color}">${msg}</span>\\n`;
            }

            function stopStream() {
                if (eventSource) {
                    eventSource.close();
                    log('[STOPPED]', 'red');
                    eventSource = null;
                }
            }

            function testBasic() {
                stopStream();
                output.innerHTML = '';
                log('Connecting to basic SSE...', 'blue');

                // EventSource is the browser's native SSE client
                eventSource = new EventSource('/sse/basic');

                // Default message handler
                eventSource.onmessage = (e) => {
                    log(`Received: ${e.data}`);
                };

                // Named event handler
                eventSource.addEventListener('complete', (e) => {
                    log(`Complete: ${e.data}`, 'green');
                    eventSource.close();
                });

                eventSource.onerror = (e) => {
                    log('Connection error', 'red');
                };
            }

            function testNamedEvents() {
                stopStream();
                output.innerHTML = '';
                log('Connecting to named events SSE...', 'blue');

                eventSource = new EventSource('/sse/named-events');

                eventSource.addEventListener('system', (e) => {
                    const data = JSON.parse(e.data);
                    log(`[SYSTEM] ${data.status}`, 'purple');
                });

                eventSource.addEventListener('progress', (e) => {
                    const data = JSON.parse(e.data);
                    log(`[PROGRESS] ${data.progress}% - ${data.step}`, 'orange');
                });

                eventSource.addEventListener('token', (e) => {
                    const data = JSON.parse(e.data);
                    // Append token without newline — like ChatGPT
                    output.innerHTML += data.token + ' ';
                });

                eventSource.addEventListener('complete', (e) => {
                    const data = JSON.parse(e.data);
                    log(`\\n[COMPLETE] ${data.message} (${data.total_tokens} tokens)`, 'green');
                    eventSource.close();
                });
            }
        </script>
    </body>
    </html>
    """