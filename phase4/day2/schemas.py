from typing import List, Optional
from pydantic import BaseModel, Field

# ============================================================
# USER SCHEMAS
# ============================================================

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str

    class Config:
        from_attributes = True


class UserProfileResponse(UserResponse):
    posts: List["PostResponse"] = []


# ============================================================
# POST SCHEMAS
# ============================================================

class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    tags: List[str] = []


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    status: str
    author_id: int

    class Config:
        from_attributes = True


class PostWithAuthorResponse(PostResponse):
    author: UserResponse


# Handle forward references
UserProfileResponse.model_rebuild()