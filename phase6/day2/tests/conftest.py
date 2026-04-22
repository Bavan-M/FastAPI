import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

import pytest
from app.main import create_app
import pytest_asyncio
from app.dependencies import get_llm_service,get_current_user
import app.dependencies as deps
from httpx import AsyncClient,ASGITransport

class MockLLMService:
    """
    Fake LLM service for tests.
    Returns instantly — no real API calls.
    Deterministic — always returns same response.
    Free — no API costs during testing.
    """
    async def generate(self,prompt:str,model:str,max_tokens:int)->dict:
        return {
            "response":f"Mock response to {prompt[:20]}",
            "model":model,
            "tokens_used":100
        }
    async def is_available(self)->bool:
        return True
    

class UnavailableLLMService:
    """LLM service that always fails — for error testing"""
    async def generate(self,prompt:str,model:str,max_tokens:int)->dict:
        raise Exception("LLM service unavailable")
    
    async def is_available(self)->bool:
        return False
    

# ============================================================
# FIXTURES
# ============================================================
# If your fixture has NO 'await' → use @pytest.fixture
# If your fixture uses 'await' inside → needs @pytest_asyncio.fixture
@pytest.fixture
def app():
    """Fresh app instance for each test.
    Prevents test pollution — one test's state
    doesn't affect another test.
    Your real app might have:
        In-memory database
        Global variables
        Cached data
        Configuration settings
        Sharing these between tests = 💣
    Fresh copy for each test = ✅ Peace of mind
    """
    return create_app()

@pytest_asyncio.fixture
async def client(app):
    """
    Async HTTP client for testing.
    ASGITransport lets us test without running a real server.
    No ports, no network — pure in-process testing.
    Layer	                What it replaces	Benefit
    ASGITransport	        Real network	    No ports needed
    dependency_overrides	Real AI API	        Free, fast, predictable
    MockLLMService	        Real OpenAI	        No $0.50 per test
    """
    app.dependency_overrides[get_llm_service]=lambda : MockLLMService()
    # AsyncClient = A fake web browser that can make HTTP requests without actually using a network.
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client
    # Clean up overrides after test
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def auth_client(app):
    """Client pre-configured with Bob's auth token"""
    app.dependency_overrides[get_llm_service]=lambda: MockLLMService() # Without lambda the mock would run immediately when the test starts, not when the app actually needs it.

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization","Bearer token-bob"}
    ) as client:
        yield client
    
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def admin_client(app):
    """Client pre-configured with admin token"""
    app.dependency_overrides[get_llm_service]=lambda : MockLLMService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization":"Bearer token-alice"}
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(app):
    """Client pre-configured with regular user token"""
    app.dependency_overrides[get_llm_service]=lambda : MockLLMService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization":"Bearer token-bob"}
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_db():
    """
    Reset in-memory DB before each test.
    Prevents test pollution — tests are independent.
    autouse=True means it runs for EVERY test automatically.
    """

    # Save original state
    original_users=dict(deps.users_db)
    original_items=dict(deps.items_db)
    original_counter=dict(deps.item_counter)

    yield # test runs here

    # Restore original state
    deps.users_db.clear()
    deps.users_db.update(original_users)
    deps.items_db.clear()
    deps.items_db.update(original_items)
    deps.item_counter=original_counter












