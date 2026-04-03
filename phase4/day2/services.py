import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
import hashlib

from day1.sqlalchemy_basics_01 import User,UserRole,Post,PostStatus
from day2.repository import UserRepository,PostRepository,TagRepository
from day2.schemas import UserCreate,PostCreate

pwd_context=CryptContext(schemes=["argon2"],deprecated="auto")


class UserService:
    def __init__(self,db:AsyncSession):
        self.db=db
        self.repo=UserRepository(db)

    def hash_password(self,plain_password:str)->str:
        pre_hash=hashlib.sha256(plain_password.encode()).hexdigest()
        return pwd_context.hash(pre_hash)

    async def register(self,data:UserCreate)->User:
        """Register a new user with business logic validation"""
        if await self.repo.username_exists(data.username):
            raise HTTPException(status_code=409,detail=f"Username {data.username} already exists")
        if await self.repo.email_exists(data.email):
            raise HTTPException(status_code=409,detail=f"Email {data.email} already exists")
        return await self.repo.create(
            username=data.username,
            email=data.email,
            hashed_password=self.hash_password(data.password),
            role=UserRole.USER
        )
    
    async def get_user(self,id:int)->User:
        """Get user by ID with error handling"""
        user=await self.repo.get_by_id(id)
        if not user:
            raise HTTPException(status_code=404,detail=f"User of userid {id} not found")
        return user
    
    async def get_user_profile(self, user_id: int) -> User:
        """Get user with their posts"""
        user = await self.repo.get_with_posts(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    
    async def deactivate_user(self, user_id: int, requesting_user: User) -> User:
        """Deactivate user - only admin or the user themselves"""
        # Business logic — authorization
        if requesting_user.role != UserRole.ADMIN and requesting_user.id != user_id:
            raise HTTPException(status_code=403, detail="Not allowed")

        user = await self.repo.deactivate(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    
    async def list_users(self,skip: int = 0,limit: int = 10,search: Optional[str] = None,role: Optional[str] = None):
        """List users with pagination and filters"""
        total = await self.repo.count()
        role_enum = UserRole(role) if role else None
        users = await self.repo.search(
            search=search, role=role_enum, skip=skip, limit=limit
        )
        return {"total": total, "users": users, "skip": skip, "limit": limit}
    
class PostService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PostRepository(db)
        self.tag_repo = TagRepository(db)

    async def create_post(self, data: PostCreate, author_id: int) -> Post:
        """Create a new post with tags"""
        # Create post
        post = await self.repo.create(
            title=data.title,
            content=data.content,
            author_id=author_id,
            status=PostStatus.DRAFT
        )

        # Handle tags — get or create each tag
        for tag_name in data.tags:
            tag = await self.tag_repo.get_or_create(tag_name.lower().strip())
            post.tags.append(tag)

        await self.db.commit()
        await self.db.refresh(post)
        return post

    async def publish_post(self, post_id: int, requesting_user: User) -> Post:
        """Publish a post - only author or admin"""
        post = await self.repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Business logic — only author or admin can publish
        if post.author_id != requesting_user.id and requesting_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Not your post")

        return await self.repo.publish(post_id)

    async def get_post(self, post_id: int) -> Post:
        """Get post with author and tags"""
        post = await self.repo.get_with_author_and_tags(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return post

    async def delete_post(self, post_id: int, requesting_user: User) -> bool:
        """Delete post - only author or admin"""
        post = await self.repo.get_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Business logic — only author or admin
        if post.author_id != requesting_user.id and requesting_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Not your post")

        return await self.repo.delete(post_id)

    async def get_feed(self, skip: int = 0, limit: int = 10):
        """Get published posts feed"""
        return await self.repo.get_published(skip=skip, limit=limit)




