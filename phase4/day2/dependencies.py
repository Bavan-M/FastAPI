from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from day2.services import UserService,PostService
from day2.database import get_db

def get_user_service(db:AsyncSession=Depends(get_db))->UserService:
    return UserService(db)

def get_post_service(db:AsyncSession=Depends(get_db))->PostService:
    return PostService(db)

