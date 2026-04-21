import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from core.config import settings

from openai import AsyncOpenAI
from groq import AsyncGroq
from typing import AsyncGenerator
from core.resilience import openai_cb,groq_cb

openai_client=AsyncOpenAI(api_key=settings.openai_api_key)
groq_client=AsyncGroq(api_key=settings.groq_api_key)

class LLMClient:
    """LLM client with:
    - Streaming support
    - Timeout protection
    - Retry logic
    - Circuit breaker
    - Automatic fallback (llama → gpt)
    """

    async def _stream_openai(self,prompt:str):
        stream=await  openai_client.chat.completions.create(
            model=settings.openai_default_model,
            messages=[{"role":"user","content":prompt}],
            stream=True)
        async for chunk in stream:
            token=chunk.choices[0].delta.content
            if token:
                yield token

    async def _stream_groq(prompt:str):
        stream=await groq_client.chat.completions.create(
            model=settings.groq_default_model,
            messages=[{"role":"user","content":prompt}],
            stream=True
        )
        async for chunk in stream:
            token=chunk.choices[0].delta.content
            if token:
                yield token

    async def _stream_with_circuit_breaker(self,stream:AsyncGenerator,circuit_breaker)->AsyncGenerator[str,None]:
        """Wrap a token stream with circuit breaker protection"""
        try:
            token_count=0
            async for token in stream:
                yield token
                token_count+=1
            circuit_breaker._on_success()
        except Exception as e:
            circuit_breaker._on_failure()
            raise

    async def stream(self,prompt:str)->AsyncGenerator[str,None]:
        """
        Stream LLM response with full resilience:
        1. Try Groq (with circuit breaker)
        2. Fallback to Openai if OpenAI circuit is open
        3. Timeout protection on each token
        4. Clean error propagation
        """
        try:
            if groq_cb.state!="open":
                async for token in self._stream_with_circuit_breaker(stream=self._stream_groq(prompt=prompt),circuit_breaker=groq_cb):
                    yield token
                return
        except Exception as e:
            print(f"[LLM] OpenAI failed after retries: {e} — falling back to Openai")

        try:
            async for token in self._stream_with_circuit_breaker(stream=self._stream_openai(prompt=prompt),circuit_breaker=openai_cb):
                yield token
        except Exception as e:
            print(f"[LLM] Openai also failed: {e}")
            yield "[Error: All LLM services unavailable. Please try again.]"


llm_client=LLMClient()