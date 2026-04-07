import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI
from typing import AsyncGenerator,Generator
import asyncio
from fastapi.responses import StreamingResponse
import json
import time


app=FastAPI(title="Streaming Response Demo")

# BASIC STREAMING
async def generate_text_chunks(text:str,delay:float=0.1)->AsyncGenerator[str,None]:
    words=text.split()
    for word in words:
        yield word + " "
        await asyncio.sleep(delay)


@app.get("/stream/basic")
async def stream_basic():
    text = "FastAPI streaming is powerful for Gen AI applications because it allows real-time token delivery to the client."
    return StreamingResponse(generate_text_chunks(text),media_type="text/plain")


# STREAMING JSON — like OpenAI's API
async def generate_json_stream(prompt:str)->AsyncGenerator[str,None]:
    """Stream JSON chunks - each chunk is a complete JSON object.
    This is exactly how OpenAI's streaming API works.
    """
    words=f"Here is my response to : {prompt}".split()
    for i,word in enumerate(words):
        chunk={
            "id":f"chunk_{i}",
            "object":"chat.completion.chunk",
            "choices":[{
                "delta":{"content":word+" "},
                "index":0,
                "finish_reason":None if i<len(words)-1 else "stop"
            }]
        }
        yield json.dumps(chunk)+"\n"
        await asyncio.sleep(0.1)

    yield "data:[DONE]\n\n"

@app.post("/stream/json")
async def stream_json(prompt:str):
    return StreamingResponse(
        generate_json_stream(prompt),
        media_type="application/x-ndjson"
    )

# STREAMING WITH HEADERS
async def generate_with_metadata(prompt:str)->AsyncGenerator[str,None]:
    total_tokens=0
    words=f"Streaming response for {prompt}".split()
    for word in words:
        total_tokens+=1
        yield word
        await asyncio.sleep(0.1)
    yield f"\n[total_tokens: {total_tokens}]"

@app.post("/stream/with-headers")
async def stream_with_headers(prompt:str):
    return StreamingResponse(
        generate_with_metadata(prompt),
        media_type="text/plain",
        headers={
            "X-Model":"gpt-4-simulated",
            "X-Stream":"true",
            "Cache-Control":"no-cache",
            "Transfer-Encoding":"chunked"
        }
    )

# STREAMING FILE DOWNLOAD — large files
async def generate_large_file()->AsyncGenerator[bytes,None]:
    """Stream a large file in chunks - never loads entire file in memory.
    Great for - exporting chat history,document downloads
    """
    chunk_size=1024
    for i in range(10):
        chunk=f"chunk_{i}:"+"x"*chunk_size+"\n"
        yield chunk.encode()
        await asyncio.sleep(1.0)

@app.get("/stream/files")
async def stream_files():
    return StreamingResponse(
        generate_large_file(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=export.txt"
        }
    )
# SYNC GENERATOR — for CPU-bound streaming
def sync_generator(items:list)->Generator[str,None,None]:
    for item in items:
        time.sleep(1.0)
        yield f"{item}\n"


@app.get("/stream/sync")
def stream_sync():
    items=[f"item_{i}" for i in range(10)]
    return StreamingResponse(
        sync_generator(items),
        media_type="text/plain"
    )


# STREAMING WITH ERROR HANDLING
async def generate_with_error_handling(prompt:str)->AsyncGenerator[str,None]:
    try:
        words=prompt.split()
        for i,word in enumerate(words):
            if word=="ERROR":
                raise ValueError("LLM API error during generation")
            yield word+ " "
            await asyncio.sleep(0.1)

    except Exception as e:
        # Can't change status code mid-stream (headers already sent)
        # Best practice: send error as final chunk
        yield f"\n[ERROR : {str(e)}]"

    finally:
        # Always runs — good for cleanup
        yield "\n[stream complete]"

@app.post("/stream/safe")
async def stream_safe(prompt:str):
    return StreamingResponse(
        generate_with_error_handling(prompt),
        media_type="text/plain"
    )