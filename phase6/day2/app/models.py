from enum import Enum
from pydantic import BaseModel,Field
from datetime import datetime
from typing import Optional

class UserRole(str,Enum):
    ADMIN="admin"
    USER="user"

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email:    str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id:         int
    username:   str
    email:      str
    role:       UserRole
    created_at: datetime


class GenerateRequest(BaseModel):
    prompt:     str = Field(..., min_length=1, max_length=4000)
    model:      str = "gpt-4"
    max_tokens: int = Field(default=512, ge=1, le=4096)


class GenerateResponse(BaseModel):
    prompt:     str
    response:   str
    model:      str
    tokens_used: int
    request_id: Optional[str] = None


class ItemCreate(BaseModel):
    title:       str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price:       float = Field(..., gt=0)


class ItemResponse(ItemCreate):
    id:         int
    owner_id:   int
    created_at: datetime
