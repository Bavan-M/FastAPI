import asyncio
import json
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse,HTMLResponse
from typing import AsyncGenerator,Optional
from pydantic import BaseModel
import time

app=FastAPI(title="LLM Streaming")

class SimulatedLLM:
    """
    Simulates OpenAI/Anthropic streaming response.
    In production replace with:

    # OpenAI:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    async with client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        stream=True
    ) as stream:
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # Anthropic:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    async with client.messages.stream(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        async for text in stream.text_stream:
            yield text
    """
    async def stream_tokens(self,prompt:str,model:str="gpt-4",max_tokens:int=100)->AsyncGenerator[str,None]:
        response = f"This is a simulated streaming response to your prompt about {prompt[:30]}. I am generating tokens one by one to simulate how real LLM APIs like OpenAI and Anthropic stream their responses back to clients in production systems."
        tokens=response.split()[:max_tokens]
        for token in tokens:
            yield token +" "
            await asyncio.sleep(0.3)


llm=SimulatedLLM()

class ChatMessage(BaseModel):
    role:str
    content:str

class StreamRequest(BaseModel):
    prompt:str
    model:str="gpt-4o"
    max_tokens:int=512
    stream:bool=True
    system_prompt:Optional[str]=None


# PATTERN 1 — Simple LLM streaming
async def stream_llm_plain(prompt:str)->AsyncGenerator[str,None]:
    async for token in llm.stream_tokens(prompt):
        yield token

@app.post("/llm/stream/plain")
async def stream_plain(prompt:str):
    return StreamingResponse(
        stream_llm_plain(prompt),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )

# PATTERN 2 — OpenAI-compatible streaming format
async def stream_openai_format(request:StreamRequest)->AsyncGenerator[str,None]:
    """Stream in OpenAI's exact format.
    Frontend code written for OpenAI works with your API too.
    """
    created=int(time.time())
    completion_id=f"completionid_{created}"
    total_tokens=0

    async for token in llm.stream_tokens(request.prompt,request.model):
        total_tokens+=1
        chunk={
            "id":completion_id,
            "object":"chat.completion.chunk",
            "created":created,
            "model":request.model,
            "choices":[{
                "index":0,
                "delta":{"content":token},
                "finish_reason":None
            }]
        }
        yield f"data : {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0)

    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": request.model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }],
        "usage": {"total_tokens": total_tokens}
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/llm/stream/openai-format")
async def stream_openai(request: StreamRequest):
    """OpenAI-compatible streaming endpoint"""
    return StreamingResponse(
        stream_openai_format(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# PATTERN 3 — SSE with named events (cleanest for frontend)
async def stream_sse_events(request:StreamRequest,http_request:Request)->AsyncGenerator[str,None]:
    """SSE with named events — cleanest for frontend integration.
    Frontend uses EventSource and handles each event type separately.
    """
    total_tokens=0
    try:
        # Send start event
        yield f"event:start\ndata: {json.dumps({"model":request.model,"prompt":request.prompt[:50]})}\n\n"

        # Stream tokens
        async for token in llm.stream_tokens(request.prompt,request.model):
            # Check if client disconnected — stop wasting compute
            if await http_request.is_disconnected():
                print("[LLM] Client disconnected — stopping generation")
                break
            total_tokens+=1
            yield f"event:token\ndata:{json.dumps({"token":token,"index":total_tokens})}\n\n"

        # Send completion event with usage stats
        yield f"event:done\ndata: {json.dumps({"total_tokens":total_tokens,"finish_reason":"stop"})}\n\n"

    except asyncio.CancelledError:
        yield f"event: error\ndata: {json.dumps({'error': 'Stream cancelled'})}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

@app.post("/llm/stream/sse")
async def stream_sse(request:StreamRequest,http_request:Request):
    """SSE streaming with named events"""
    return StreamingResponse(
        stream_sse_events(request,http_request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# PATTERN 4 — Conditional streaming
@app.post("/llm/generate")
async def generate(request:StreamRequest):
    """Single endpoint that handles both streaming and non-streaming.
    Client decides via stream=true/false in request body.
    """
    if request.stream:
        return StreamingResponse(
            stream_openai_format(request),
            media_type="text/event-stream",
            headers={"Cache-Control":"no-cache"}
        )
    else:
        # Non-streaming — collect all tokens and return at once
        full_response=""
        total_tokens=0
        async for token in llm.stream_tokens(request.prompt,request.model):
            full_response+=token
            total_tokens+=1
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "model": request.model,
            "choices": [{
                "message": {"role": "assistant", "content": full_response},
                "finish_reason": "stop"
            }],
            "usage": {"total_tokens": total_tokens}
        }
    
@app.get("/", response_class=HTMLResponse)
def chat_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>LLM Streaming Test</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            #output { border: 1px solid #ccc; padding: 15px; min-height: 200px;
                      white-space: pre-wrap; font-family: monospace; margin: 10px 0; }
            button { padding: 10px 20px; margin: 5px; cursor: pointer; }
            input, textarea { width: 100%; padding: 8px; margin: 5px 0; }
            .token { color: #333; }
            .meta  { color: #888; font-size: 0.85em; }
            .error { color: red; }
        </style>
    </head>
    <body>
        <h2>🤖 LLM Streaming Test</h2>

        <textarea id="prompt" rows="3" placeholder="Enter your prompt...">Explain how RAG pipelines work in Gen AI</textarea>

        <div>
            <button onclick="streamPlain()">Stream Plain Text</button>
            <button onclick="streamSSE()">Stream SSE Events</button>
            <button onclick="streamOpenAI()">Stream OpenAI Format</button>
            <button onclick="stopStream()">⛔ Stop</button>
        </div>

        <div id="stats" class="meta"></div>
        <div id="output"></div>

        <script>
            let eventSource = null;
            let tokenCount = 0;
            let startTime = null;

            const output = document.getElementById('output');
            const stats  = document.getElementById('stats');

            function clearOutput() {
                output.innerHTML = '';
                stats.innerHTML = '';
                tokenCount = 0;
                startTime = Date.now();
            }

            function stopStream() {
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                    output.innerHTML += '\\n[STOPPED]';
                }
            }

            // Pattern 1 — Plain text streaming via fetch
            async function streamPlain() {
                clearOutput();
                const prompt = document.getElementById('prompt').value;

                const response = await fetch(
                    `/llm/stream/plain?prompt=${encodeURIComponent(prompt)}`,
                    { method: 'POST' }
                );

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    const text = decoder.decode(value);
                    output.innerHTML += `<span class="token">${text}</span>`;
                    tokenCount++;
                    stats.innerHTML = `Tokens: ${tokenCount} | Time: ${((Date.now()-startTime)/1000).toFixed(1)}s`;
                }
            }

            // Pattern 2 — SSE with named events via EventSource
            function streamSSE() {
                clearOutput();
                stopStream();
                const prompt = document.getElementById('prompt').value;

                // Note: EventSource only supports GET
                // For POST we use fetch with SSE-like reading
                fetch('/llm/stream/sse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt, stream: true })
                }).then(response => {
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    function processChunk({ done, value }) {
                        if (done) return;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\\n');
                        buffer = lines.pop();

                        let currentEvent = 'message';
                        for (const line of lines) {
                            if (line.startsWith('event:')) {
                                currentEvent = line.slice(6).trim();
                            } else if (line.startsWith('data:')) {
                                const data = JSON.parse(line.slice(5).trim());
                                if (currentEvent === 'token') {
                                    output.innerHTML += `<span class="token">${data.token}</span>`;
                                    tokenCount = data.index;
                                    stats.innerHTML = `Tokens: ${tokenCount} | Time: ${((Date.now()-startTime)/1000).toFixed(1)}s`;
                                } else if (currentEvent === 'done') {
                                    output.innerHTML += `\\n<span class="meta">[Done: ${data.total_tokens} tokens]</span>`;
                                } else if (currentEvent === 'error') {
                                    output.innerHTML += `<span class="error">[Error: ${data.error}]</span>`;
                                }
                                currentEvent = 'message';
                            }
                        }
                        return reader.read().then(processChunk);
                    }
                    reader.read().then(processChunk);
                });
            }

            // Pattern 3 — OpenAI format via fetch
            async function streamOpenAI() {
                clearOutput();
                const prompt = document.getElementById('prompt').value;

                const response = await fetch('/llm/stream/openai-format', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt, model: 'gpt-4', stream: true })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6);
                            if (data === '[DONE]') {
                                output.innerHTML += '\\n<span class="meta">[Complete]</span>';
                                continue;
                            }
                            try {
                                const chunk = JSON.parse(data);
                                const content = chunk.choices?.[0]?.delta?.content;
                                if (content) {
                                    output.innerHTML += `<span class="token">${content}</span>`;
                                    tokenCount++;
                                    stats.innerHTML = `Tokens: ${tokenCount} | Time: ${((Date.now()-startTime)/1000).toFixed(1)}s`;
                                }
                            } catch(e) {}
                        }
                    }
                }
            }
        </script>
    </body>
    </html>
    """