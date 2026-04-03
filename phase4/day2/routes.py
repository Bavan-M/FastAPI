import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from typing import List,Optional
from fastapi import APIRouter,Depends,HTTPException

from day2.schemas import UserCreate,UserResponse,UserProfileResponse,PostCreate,PostResponse,PostWithAuthorResponse
from day2.services import UserService,PostService
from day2.dependencies import get_post_service,get_user_service,get_db

user_router=APIRouter(prefix="/users",tags=["users"])
post_router=APIRouter(prefix="/posts",tags=["posts"])

@user_router.post("",response_model=UserResponse,status_code=201)
async def register_user(data:UserCreate,service:UserService=Depends(get_user_service)):
    """Register a new user"""
    return await service.register(data)

@user_router.get("", response_model=dict)
async def list_users(skip: int = 0,limit: int = 10,search: Optional[str] = None,role: Optional[str] = None,service: UserService = Depends(get_user_service)):
    """List all users with pagination and filters"""
    return await service.list_users(skip, limit, search, role)

@user_router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int,service: UserService = Depends(get_user_service)):
    """Get user by ID"""
    return await service.get_user(user_id)

@user_router.get("/{user_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(user_id: int,service: UserService = Depends(get_user_service)):
    """Get user with their posts"""
    return await service.get_user_profile(user_id)

@user_router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(user_id: int,requesting_user_id: int,user_service: UserService = Depends(get_user_service)):# In real app, get from JWT token
    """Deactivate a user (admin or self only)"""
    requesting_user = await user_service.get_user(requesting_user_id)
    return await user_service.deactivate_user(user_id, requesting_user)

@post_router.post("", response_model=PostResponse, status_code=201)
async def create_post(
    data: PostCreate,
    author_id: int,  # In real app, get from JWT token
    service: PostService = Depends(get_post_service)
):
    """Create a new post"""
    return await service.create_post(data, author_id)


@post_router.get("/feed", response_model=List[PostResponse])
async def get_feed(
    skip: int = 0,
    limit: int = 10,
    service: PostService = Depends(get_post_service)
):
    """Get published posts feed"""
    return await service.get_feed(skip, limit)


@post_router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    service: PostService = Depends(get_post_service)
):
    """Get post by ID"""
    return await service.get_post(post_id)


@post_router.patch("/{post_id}/publish", response_model=PostResponse)
async def publish_post(
    post_id: int,
    requesting_user_id: int,  # In real app, get from JWT token
    post_service: PostService = Depends(get_post_service),
    user_service: UserService = Depends(get_user_service)
):
    """Publish a post (author or admin only)"""
    requesting_user = await user_service.get_user(requesting_user_id)
    return await post_service.publish_post(post_id, requesting_user)


@post_router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    requesting_user_id: int,  # In real app, get from JWT token
    post_service: PostService = Depends(get_post_service),
    user_service: UserService = Depends(get_user_service)
):
    """Delete a post (author or admin only)"""
    requesting_user = await user_service.get_user(requesting_user_id)
    await post_service.delete_post(post_id, requesting_user)
    return None