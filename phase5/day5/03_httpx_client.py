import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI
from contextlib import asynccontextmanager
import httpx


http_client:httpx.AsyncClient=None

@asynccontextmanager
async def lifespan(app:FastAPI):
    global http_client
    # Create shared client — connection pool reused across requests
    http_client=httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0, #How long Your server establishes a TCP connection to OpenAI's server (handshake)
            read=30.0, #How long Your server waits for OpenAI to PROCESS and SEND BACK the response
            write=10.0, #How long Your server sends the request data (headers, JSON body) to OpenAI
            pool=5.0 #How long Your server waits to get an available connection from the pool
        ),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20
        ),
        headers={"User-Agent":"MyGenAIApp/1.0"}
    )
    print("✅ HTTP client ready")
    yield
    await http_client.aclose()
    print("✅ HTTP client closed")

app=FastAPI(title="httpx Client Demo",lifespan=lifespan)


@app.get("/http/basic")
async def basic_requests():
    """GET, POST, headers, params"""
    # GET request
    response=await http_client.get(url="https://httpbin.org/get",params={"foo":"bar","baz":"qux"})
    response.raise_for_status()
    get_data=response.json()

    # POST with JSON body
    post_response=await http_client.post(
        url="https://httpbin.org/post",
        json={"prompt":"Hello","model":"htp-3.5-turbo"},
        headers={"Authorization":"Beare fake-token"}
    )
    post_data=post_response.json()

    return {
        "get_url": get_data.get("url"),
        "post_json": post_data.get("json"),
        "status_codes": {
            "get": response.status_code,
            "post": post_response.status_code
        }
    }
