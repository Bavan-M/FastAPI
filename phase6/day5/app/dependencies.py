import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import Header, HTTPException, Depends
from typing import Optional


# Fake users — replace with real DB + JWT in production
FAKE_USERS = {
    "token-alice": {"id": 1, "username": "alice", "role": "admin"},
    "token-bob":   {"id": 2, "username": "bob",   "role": "user"},
}


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = authorization.split(" ")[1]
    user  = FAKE_USERS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user