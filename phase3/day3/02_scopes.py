import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes
)
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

app = FastAPI(title="Scopes Demo")

SECRET_KEY = "your-super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context=CryptContext(schemes="argon2",deprecated="auto")
oauth2=OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(passowrd:str,hash_password:str)->bool:
    pre_hashed=hashlib.sha256(passowrd.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hash_password)

# Define available scopes — shown in Swagger UI
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scopes={
        "tasks:read":      "Read your tasks",
        "tasks:write":     "Create and update tasks",
        "tasks:delete":    "Delete tasks",
        "users:read":      "Read user profiles",
        "users:manage":    "Manage all users",
        "ai:llm":          "Use LLM generation",
        "ai:embeddings":   "Use embedding endpoints",
        "analytics:read":  "View analytics data",
    }
)

# User → what scopes they're allowed to request
fake_users_db = {
    "alice": {
        "id": 1, "username": "alice",
        "hashed_password": hash_password("pass123"),
        "allowed_scopes": [
            "tasks:read", "tasks:write", "tasks:delete",
            "users:read", "users:manage",
            "ai:llm", "ai:embeddings", "analytics:read"
        ]
    },
    "bob": {
        "id": 2, "username": "bob",
        "hashed_password": hash_password("pass123"),
        "allowed_scopes": ["tasks:read", "tasks:write", "ai:llm", "ai:embeddings"]
    },
    "ai_service": {
        "id": 3, "username": "ai_service",
        "hashed_password": hash_password("service123"),
        "allowed_scopes": ["ai:embeddings"]   # service account — very limited
    }
}


# ============================================================
# TOKEN — now includes scopes
# ============================================================

def create_access_token(data: dict, scopes: List[str]) -> str:
    to_encode = data.copy()
    to_encode.update({
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "scopes": scopes    # embed granted scopes in token
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ============================================================
# SCHEMAS
# ============================================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    granted_scopes: List[str]


class TokenData(BaseModel):
    username: Optional[str] = None
    scopes: List[str] = []


# ============================================================
# DEPENDENCY — validates required scopes
# ============================================================

async def get_current_user(
    security_scopes: SecurityScopes,   # injected by FastAPI — contains required scopes
    token: str = Depends(oauth2_scheme)
) -> dict:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value}
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
        token_scopes = payload.get("scopes", [])
        token_data = TokenData(username=username, scopes=token_scopes)
    except JWTError:
        raise credentials_exception

    user = fake_users_db.get(token_data.username)
    if not user:
        raise credentials_exception

    # Check every required scope is in the token
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: '{scope}'",
                headers={"WWW-Authenticate": authenticate_value}
            )

    user["token_scopes"] = token_data.scopes
    return user


# ============================================================
# ROUTES
# ============================================================

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = fake_users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Only grant scopes the user is allowed to have
    requested_scopes = form_data.scopes  # client specifies what it needs
    allowed = user["allowed_scopes"]
    granted_scopes = [s for s in requested_scopes if s in allowed]

    # If no scopes requested — grant all allowed scopes
    if not requested_scopes:
        granted_scopes = allowed

    token = create_access_token(
        data={"sub": user["username"]},
        scopes=granted_scopes
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "granted_scopes": granted_scopes
    }


# Security() instead of Depends() — used when scopes are required
@app.get("/tasks")
def get_tasks(
    current_user: dict = Security(get_current_user, scopes=["tasks:read"])
):
    return {"tasks": [], "user": current_user["username"]}


@app.post("/tasks")
def create_task(
    title: str,
    current_user: dict = Security(get_current_user, scopes=["tasks:write"])
):
    return {"task": title, "created_by": current_user["username"]}


@app.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    current_user: dict = Security(get_current_user, scopes=["tasks:delete"])
):
    return {"deleted": task_id}


@app.post("/ai/generate")
def generate(
    prompt: str,
    current_user: dict = Security(get_current_user, scopes=["ai:llm"])
):
    return {"response": f"LLM response to: {prompt}"}


@app.post("/ai/embed")
def embed(
    text: str,
    current_user: dict = Security(get_current_user, scopes=["ai:embeddings"])
):
    return {"embedding": [0.1, 0.2, 0.3], "text": text}


@app.get("/analytics")
def analytics(
    current_user: dict = Security(get_current_user, scopes=["analytics:read"])
):
    return {"total_tasks": 100, "completion_rate": "78%"}


# Route requiring MULTIPLE scopes
@app.get("/admin/full-report")
def full_report(
    current_user: dict = Security(
        get_current_user,
        scopes=["analytics:read", "users:manage"]  # needs BOTH
    )
):
    return {"report": "full admin report", "user": current_user["username"]}