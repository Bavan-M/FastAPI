import pytest
import asyncio
from unittest.mock import AsyncMock,MagicMock,patch
from app.dependencies import get_llm_service,get_current_user
from httpx import AsyncClient,ASGITransport
from tests.conftest import MockLLMService,UnavailableLLMService

# ============================================================
# MOCKING PATTERNS
# ============================================================

@pytest.mark.asyncio
async def test_mock_with_asyncmock(app):
    """
    AsyncMock — the right way to mock async functions.
    Regular MagicMock doesn't work for async — use AsyncMock.
    """

    # Create a mock that returns specific data
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value={
        "response":    "Mocked response about RAG",
        "model":       "gpt-4",
        "tokens_used": 250
    })

    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer token-alice"}
    ) as client:
        response = await client.post(
            "/api/v1/llm/generate",
            json={"prompt": "What is RAG?", "model": "gpt-4"}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["tokens_used"] == 250
    assert "RAG" in data["response"]

    # Verify mock was called with correct arguments
    mock_llm.generate.assert_called_once()
    call_args = mock_llm.generate.call_args
    assert call_args[0][0] == "What is RAG?"     # first positional arg = prompt
    assert call_args[0][1] == "gpt-4"             # second = model

@pytest.mark.asyncio
async def test_mosk_raises_exception(app):
    """Mock an exception to test error handling"""
    mock_llm=AsyncMock()
    mock_llm.generate=AsyncMock(side_effect=Exception("Open AI rate limit exceeded"))

    app.dependency_overrides[get_llm_service]=lambda : mock_llm

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization":"Bearer token-alice"}
    ) as client:
        response=await client.post("/api/v1/llm/generate",json={"prompt":"Hello"})
    app.dependency_overrides.clear()

    assert response.status_code in (500,503)





@pytest.mark.asyncio
async def test_mock_call_count(app):
    """Verify a dependency is called exactly once"""
    from app.dependencies import get_llm_service
    from httpx import AsyncClient, ASGITransport

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value={
        "response": "test", "model": "gpt-4", "tokens_used": 50
    })

    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer token-alice"}
    ) as client:
        await client.post("/api/v1/llm/generate", json={"prompt": "test"})
        await client.post("/api/v1/llm/generate", json={"prompt": "test2"})

    app.dependency_overrides.clear()

    # Called exactly twice — once per request
    assert mock_llm.generate.call_count == 2

@pytest.mark.asyncio
# since we are not checking AUTHENTICATION
# and the test does not needs a LOGGED-IN user 
# we need to use app instead of auth_client and client
async def test_dependency_override_auth(app):
    """
    Override auth dependency entirely.
    Useful when testing routes without caring about auth.
    To test if the our app correctly returns the user data that we inject via dependency override
    """
    fake_admin={"id":99,"username":"test_admin","role":"admin","email":"test@gmail.com"}

    app.dependency_overrides[get_current_user]=lambda : fake_admin
    app.dependency_overrides[get_llm_service]=lambda : MockLLMService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # since we have override the authorization with fake_admin we do not need to authorize for the below /api/v1/auth/me
        response=await client.get("api/v1/auth/me")
    app.dependency_overrides.clear()

    assert response.status_code==200
    assert response.json()["username"] == "test_admin"


# ============================================================
# INTEGRATION TESTS
# ============================================================
@pytest.mark.asyncio
# since we are not checking AUTHENTICATION
# and the test needs a LOGGED-IN user 
# we need to use auth_client instead of app and client
async def test_full_user_workflow(auth_client):
    """
    Integration test — tests a complete user workflow.
    Multiple steps that depend on each other.
    """
    # Step 1 — Get current user profile
    me_res=await auth_client.get("/api/v1/auth/me")
    assert me_res.status_code==200
    user=me_res.json()
    assert user["username"]=="alice"


    # Step 2 — Create multiple items
    item_ids=[]
    for i in range(3):
        res=await auth_client.post("/api/v1/items",json={"title":f"Item {i}","price":float(i+1)*10})
        assert res.status_code==201
        item_ids.append(res.json()["id"])

    
    # Step 3 — List items — should see all 3
    list_res=await auth_client.get("/api/v1/items")
    assert len(list_res.json())==3


    # Step 4 — Get specific item
    get_res = await auth_client.get(f"/api/v1/items/{item_ids[0]}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Item 0"

    # Step 5 — Delete one item
    del_res = await auth_client.delete(f"/api/v1/items/{item_ids[0]}")
    assert del_res.status_code == 204

    # Step 6 — List items — should see only 2 now
    final_list = await auth_client.get("/api/v1/items")
    assert len(final_list.json()) == 2

@pytest.mark.asyncio
async def test_full_llm_workflow(auth_client):
    """Integration test for LLM generation flow"""
    # Check LLM is available
    status = await auth_client.get("/api/v1/llm/status")
    assert status.json()["available"] is True

    # Generate response
    gen_res = await auth_client.post(
        "/api/v1/llm/generate",
        json={
            "prompt":     "Explain vector databases for RAG",
            "model":      "gpt-4",
            "max_tokens": 1000
        }
    )
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert data["model"]      == "gpt-4"
    assert data["tokens_used"] > 0
    assert len(data["response"]) > 0
    assert data["request_id"] is not None


# ============================================================
# PARAMETRIZED TESTS — test many cases with one function
# ============================================================

# Instead of writing 3 separate tests, you write 1 test that runs 3 times with different inputs.

@pytest.mark.asyncio
@pytest.mark.parametrize("prompt,expected_status", [("Valid prompt here",200),("",422),("x"*8400,422)])
async def test_generate_prompt_validation(auth_client,prompt,expected_status):
    """
    Parametrize runs this test 3 times with different inputs.
    Much cleaner than writing 3 separate test functions.
    """
    response=await auth_client.post("/api/v1/llm/generate",json={"prompt":prompt})
    assert response.status_code==expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize("token,expected_status", [
    ("token-alice",        200),   # valid admin token
    ("token-bob",          200),   # valid user token
    ("invalid-token",      401),   # bad token
    ("",                   401),   # empty token
])
async def test_auth_with_various_tokens(client, token, expected_status):
    """Test auth with multiple token types"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == expected_status

        
