from fastapi import Header, HTTPException, Depends
from typing import Optional
from app.services import LLMService


# In-memory stores (replace with DB in real app)
users_db: dict = {
    "token-alice": {"id": 1, "username": "alice", "role": "admin",
                    "email": "alice@test.com"},
    "token-bob":   {"id": 2, "username": "bob",   "role": "user",
                    "email": "bob@test.com"}
}

items_db: dict = {}
item_counter = 1


# ============================================================
# DEPENDENCIES
# ============================================================

async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    token = authorization.split(" ")[1]
    user  = users_db.get(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


async def get_llm_service():
    """
    Returns an LLM service instance.
    In tests we override this with a mock.
    This is the key to fast, free, deterministic tests.
    """
    return LLMService()