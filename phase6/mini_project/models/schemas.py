import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email:    str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id:         int
    username:   str
    email:      str
    role:       str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int


class ItemCreate(BaseModel):
    title:       str   = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price:       float = Field(..., gt=0)


class ItemResponse(ItemCreate):
    id:         int
    owner_id:   int
    created_at: datetime


class GenerateRequest(BaseModel):
    prompt:     str   = Field(..., min_length=1, max_length=4000)
    model:      str   = "gpt-4"
    max_tokens: int   = Field(default=512, ge=1, le=4096)
    stream:     bool  = False


class GenerateResponse(BaseModel):
    prompt:      str
    response:    str
    model:       str
    tokens_used: int
    cost_usd:    float
    latency_ms:  float
    request_id:  Optional[str] = None
    trace_id:    Optional[str] = None