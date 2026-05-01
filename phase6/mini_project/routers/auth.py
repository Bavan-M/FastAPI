import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from models.schemas import UserCreate, UserResponse, Token
from core.config import settings
from core.logging import auth_logger
import hashlib

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context   = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# In-memory store — replace with DB in production
users_db = {
    "alice": {
        "id": 1, "username": "alice", "email": "alice@test.com",
        "role": "admin",
        "hashed_password": hash_password("Password123"),
        "created_at": datetime.now(timezone.utc).isoformat()
    },
    "bob": {
        "id": 2, "username": "bob", "email": "bob@test.com",
        "role": "user",
        "hashed_password": hash_password("Password123"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
}


def create_token(username: str, role: str) -> str:
    return jwt.encode(
        {
            "sub":  username,
            "role": role,
            "exp":  datetime.now(timezone.utc) + timedelta(
                        minutes=settings.token_expire_minutes)
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload  = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm]
        )
        username = payload.get("sub")
        user     = users_db.get(username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def send_welcome_email(email: str, username: str):
    import time
    time.sleep(0.5)
    auth_logger.bind(email=email, username=username).info("Welcome email sent")


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: UserCreate, background_tasks: BackgroundTasks):
    if data.username in users_db:
        raise HTTPException(status_code=409, detail="Username already taken")

    new_user = {
        "id":              len(users_db) + 1,
        "username":        data.username,
        "email":           data.email,
        "role":            "user",
        "hashed_password": hash_password(data.password),
        "created_at":      datetime.now(timezone.utc).isoformat()
    }
    users_db[data.username] = new_user
    auth_logger.bind(username=data.username).info("User registered")
    background_tasks.add_task(send_welcome_email, data.email, data.username)
    return new_user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password,
                                           user["hashed_password"]):
        auth_logger.bind(username=form_data.username).warning("Login failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["username"], user["role"])
    auth_logger.bind(username=user["username"]).info("Login successful")
    return {
        "access_token": token,
        "token_type":   "bearer",
        "expires_in":   settings.token_expire_minutes * 60
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user