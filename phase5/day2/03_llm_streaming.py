import asyncio
import json
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator,Optional
from pydantic import BaseModel

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
