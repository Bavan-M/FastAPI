from fastapi import FastAPI,Request
from slowapi import Limiter,_rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app=FastAPI(title="SlowAPI demo")

limiter=Limiter(key_func=get_remote_address)
app.state.limiter=limiter
app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)

@app.get("/items")
@limiter.limit(limit_value="60/minute")
async def get_items(request:Request):
    return {
        "items":[]
    }

@app.post("/llm/generate")
@limiter.limit("10/minute")
@limiter.limit("100/day")
async def generate(request:Request):
    return {}


