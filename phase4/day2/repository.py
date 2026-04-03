import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from typing import Optional,TypeVar,Generic,List
from day1.sqlalchemy_basics_01 import Base,User,Post,Tag,UserRole,PostStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func,and_,or_
from sqlalchemy.orm import selectinload

load_dotenv("phase4/.env")

ModelType=TypeVar("ModelType")

class BaseRepository(Generic[ModelType]):
    """Genric repository with common CRUD operations.
    Every specific repository inherits this."""
    def __init__(self,model:type[ModelType],db:AsyncSession):
        self.db=db
        self.model=model

    async def get_by_id(self,id:int)->Optional[ModelType]:
        result=await self.db.execute(select(self.model).where(self.model.id==id))
        return result.scalar_one_or_none()
    
    async def get_all(self,skip:int=0,limit:int=10)->Optional[ModelType]:
        result=await self.db.execute(select(self.model).offset(skip).limit(limit))
        return result.scalars().all()
    
    async def count(self)->int:
        result=await self.db.execute(select(func.count(self.model.id)))
        return result.scalar()
    
    async def create(self,**kwargs)->ModelType:
        obj=self.model(**kwargs)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj
    
    async def update(self,id:int,**kwargs)->Optional[ModelType]:
        obj= await self.get_by_id(id)
        if not obj :
            return None
        
        for key,value in kwargs.items():
            # First iteration: setattr(obj, "username", "new_name") → obj.username = "new_name"
            # Second iteration: setattr(obj, "email", "new@email.com") → obj.email = "new@email.com"
            # Third iteration: setattr(obj, "role", "ADMIN") → obj.role = "ADMIN"
            setattr(obj,key,value)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj
    
    async def delete(self,id:int)->bool:
        obj=self.get_by_id(id)
        if not obj:
            return False
        await self.db.delete(obj)
        await self.db.commit()
        return True
    
    async def exists(self,id:int)->bool:
        result=await self.db.execute(select(func.count(self.model.id==id)))
        return result.scalar()>0

# ============================================================
# USER REPOSITORY
# ============================================================
class UserRepository(BaseRepository[User]):
    def __init__(self,db:AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self,email:str)->Optional[User]:
        result=await self.db.execute(select(User).where(User.email==email))
        return result.scalar_one_or_none()
    
    async def get_by_username(self,username:str)->Optional[User]:
        result=await self.db.execute(select(User).where(User.username==username))
        return result.scalar_one_or_none()
    
    async def get_with_posts(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id).options(selectinload(User.posts)))
        return result.scalar_one_or_none()
    
    async def get_with_api_keys(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id).options(selectinload(User.api_keys)))
        return result.scalar_one_or_none()

    async def search(self,search: Optional[str] = None,role: Optional[UserRole] = None,is_active: Optional[bool] = None,skip: int = 0,limit: int = 10) -> List[User]:
        query = select(User)
        conditions = []

        if search:
            conditions.append(
                or_(
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%")
                )
            )
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query.offset(skip).limit(limit).order_by(User.created_at.desc()))
        return result.scalars().all()
    
    async def email_exists(self, email: str) -> bool:
        result = await self.db.execute(select(func.count(User.id)).where(User.email == email))
        return result.scalar() > 0

    async def username_exists(self, username: str) -> bool:
        result = await self.db.execute(select(func.count(User.id)).where(User.username == username))
        return result.scalar() > 0

    async def deactivate(self, user_id: int) -> Optional[User]:
        return await self.update(user_id, is_active=False)

    async def get_by_role(self, role: UserRole) -> List[User]:
        result = await self.db.execute(select(User).where(User.role == role))
        return result.scalars().all()

class PostRepository(BaseRepository[Post]):
    def __init__(self, db: AsyncSession):
        super().__init__(Post, db)

    async def get_by_author(
        self,
        author_id: int,
        status: Optional[PostStatus] = None,
        skip: int = 0,
        limit: int = 10
    ) -> List[Post]:
        query = select(Post).where(Post.author_id == author_id)
        if status:
            query = query.where(Post.status == status)
        result = await self.db.execute(
            query.offset(skip).limit(limit).order_by(Post.created_at.desc())
        )
        return result.scalars().all()

    async def get_published(self, skip: int = 0, limit: int = 10) -> List[Post]:
        result = await self.db.execute(
            select(Post)
            .where(Post.status == PostStatus.PUBLISHED)
            .options(selectinload(Post.author))   # load author in same query
            .options(selectinload(Post.tags))     # load tags in same query
            .offset(skip)
            .limit(limit)
            .order_by(Post.created_at.desc())
        )
        return result.scalars().all()

    async def get_with_author_and_tags(self, post_id: int) -> Optional[Post]:
        result = await self.db.execute(
            select(Post)
            .where(Post.id == post_id)
            .options(selectinload(Post.author))
            .options(selectinload(Post.tags))
        )
        return result.scalar_one_or_none()

    async def publish(self, post_id: int) -> Optional[Post]:
        return await self.update(post_id, status=PostStatus.PUBLISHED)

    async def count_by_author(self, author_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Post.id)).where(Post.author_id == author_id)
        )
        return result.scalar()

    async def search(self, query_str: str, skip: int = 0, limit: int = 10) -> List[Post]:
        result = await self.db.execute(
            select(Post)
            .where(
                or_(
                    Post.title.ilike(f"%{query_str}%"),
                    Post.content.ilike(f"%{query_str}%")
                )
            )
            .offset(skip).limit(limit)
        )
        return result.scalars().all()


# ============================================================
# TAG REPOSITORY
# ============================================================

class TagRepository(BaseRepository[Tag]):
    def __init__(self, db: AsyncSession):
        super().__init__(Tag, db)

    async def get_by_name(self, name: str) -> Optional[Tag]:
        result = await self.db.execute(
            select(Tag).where(Tag.name == name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> Tag:
        tag = await self.get_by_name(name)
        if not tag:
            tag = await self.create(name=name)
        return tag

    async def get_all_with_post_count(self) -> List[dict]:
        result = await self.db.execute(
            select(Tag).options(selectinload(Tag.posts))
        )
        tags = result.scalars().all()
        return [
            {"id": t.id, "name": t.name, "post_count": len(t.posts)}
            for t in tags
        ]