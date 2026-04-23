import pytest
import asyncio
from unittest.mock import AsyncMock,patch
from app.dependencies import get_llm_service
from tests.conftest import UnavailableLLMService,MockLLMService
from httpx import AsyncClient,ASGITransport

# ============================================================
# LLM GENERATION TESTS
# ============================================================
@pytest.mark.asyncio
async def test_generate_success(auth_client):
    """Happy path — generate with mock LLM"""
    # Arrange
    payload = {
        "prompt":     "Explain RAG pipelines",
        "model":      "gpt-4",
        "max_tokens": 512
    }

    # Act
    response = await auth_client.post("/api/v1/llm/generate", json=payload)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["prompt"]      == "Explain RAG pipelines"
    assert data["model"]       == "gpt-4"
    assert data["tokens_used"] == 100     # MockLLMService always returns 100
    assert "response"   in data
    assert "request_id" in data



@pytest.mark.asyncio
async def test_generate_unauthenticated(client):
    """No auth — should return 401"""
    response = await client.post(
        "/api/v1/llm/generate",
        json={"prompt": "Hello"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_empty_prompt(auth_client):
    """Empty prompt — validation should reject it"""
    response = await auth_client.post(
        "/api/v1/llm/generate",
        json={"prompt": ""}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_prompt_too_long(auth_client):
    """Prompt exceeds 4000 chars — should fail"""
    response = await auth_client.post(
        "/api/v1/llm/generate",
        json={"prompt": "x" * 4001}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_llm_status(auth_client):
    """LLM status endpoint"""
    response = await auth_client.get("/api/v1/llm/status")
    assert response.status_code == 200
    assert response.json()["available"] is True


# ============================================================
# TESTING WITH DIFFERENT MOCK BEHAVIORS
# ============================================================
@pytest.mark.asyncio
async def test_llm_service_unavailable(app):
    """
    Override dependency to simulate LLM being down.
    Tests that your API handles LLM failures gracefully.
    """
    # Override with broken LLM service
    app.dependency_overrides[get_llm_service]=lambda: UnavailableLLMService()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization":"Bearer token-alice"}
    ) as client:
        response=await client.post("/api/v1/llm/generate",json={"prompt":"Hello"})
    app.dependency_overrides.clear()

    # Should return 500 or 503 — not crash
    assert response.status_code in (500,503)


@pytest.mark.asyncio
async def test_concurrent_requests(auth_client):
    """
    Test that multiple concurrent requests work correctly.
    Critical for async FastAPI — tests event loop handling.
    """
    # Fire 10 requests concurrently
    tasks=[auth_client.post("api/v1/llm/generate",json={"prompt":f"Prompt_{i}","model":"gpt-4"}) for i in range(10)]
    response=await asyncio.gather(*tasks)

    # All should succeed
    assert  all(r.status_code==200 for r in response)
    assert len(response)==10

    # Each should have unique content
    prompts=[r.json()["prompt"] for r in response]
    assert len(set(prompts))==10




@pytest.mark.asyncio
async def test_request_isolation(app): 
    """
    Tests don't interfere with each other.
    Each test gets a fresh state.
    Isolation Test:
    1. Create item → Item exists in database
    2. Test ends → reset_db fixture RESTORES database (item is REMOVED!)
    3. Next test starts → Database is CLEAN, item is GONE
    Note : to do this autimatically we need to set autouse=True which we did in conftest.py
    """
    app.dependency_overrides[get_llm_service]=lambda :MockLLMService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization":"Bearer token-alice"}
    ) as client:
        response=await client.post("/api/v1/items",json={"title":"Isolation Test Item","price":1.0})
        assert response.status_code==201

    app.dependency_overrides.clear()
