from fastapi import Depends,Header,HTTPException
from typing import Optional

FAKE_USERS={
    "token-alice":{"id":1,"username":"Alice","role":"admin"},
    "token-bob":{"id":2,"username":"Bob","role":"user"}
}

def get_current_user(authorization:Optional[str]=Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401,detail="Missing or Invalid Authorization")

    token=authorization.split(" ")[1]
    user=FAKE_USERS.get(token)

    if not user:
        raise HTTPException(status_code=401,detail="Invalid Token")

    return user

def require_admin(user:dict=Depends(get_current_user)):
    if user['role']!="admin":
        raise HTTPException(status_code=403,detail="Admin access required")
    return user