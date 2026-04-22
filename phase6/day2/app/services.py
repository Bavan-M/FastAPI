import asyncio


class LLMService:
    """
    Real LLM service.
    In tests this gets mocked so we never
    actually call OpenAI during testing.
    """

    async def generate(self, prompt: str, model: str, max_tokens: int) -> dict:
        # In production: call OpenAI/Anthropic API
        await asyncio.sleep(1.0)   # simulates network call
        return {
            "response":   f"Real LLM response to: {prompt[:30]}",
            "model":      model,
            "tokens_used": len(prompt.split()) * 10
        }

    async def is_available(self) -> bool:
        await asyncio.sleep(0.1)
        return True