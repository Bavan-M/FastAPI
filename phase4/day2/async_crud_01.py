import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from passlib.context import CryptContext
import hashlib

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine,async_sessionmaker
from sqlalchemy import select,func,or_,and_,update,delete
from sqlalchemy.orm import selectinload

load_dotenv("phase4/.env")
from day1.sqlalchemy_basics_01 import Base,User,Post,UserRole

DATABASE_URL=os.getenv("DATABASE_URL","postgresql+asyncpg://postgres:master@localhost:5432/fastapi_phase4")

engine=create_async_engine(url=DATABASE_URL,echo=False)
AsyncSessionLocal=async_sessionmaker(bind=engine,expire_on_commit=False)
pwd_context=CryptContext(schemes=["argon2"],deprecated="auto")


def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)




async def create_user(db:AsyncSession,username:str,email:str,password:str,role:UserRole=UserRole.USER)->User:
    user=User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_post(db:AsyncSession,title:str,content:str,author_id:int)->Post:
    post=Post(
        title=title,
        content=content,
        author_id=author_id
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post

async def get_user_by_id(db:AsyncSession,user_id:int):
    result=await db.execute(select(User).where(User.id==user_id))
    return result.scalar_one_or_none() # None if not found, error if multiple

async def get_user_by_email(db:AsyncSession,email:str):
    result=await db.execute(select(User).where(User.email==email))
    return result.scalar_one_or_none()

async def get_all_users(db:AsyncSession,skip:int=0,limit:int=10):
    result=await db.execute(select(User).offset(skip).limit(limit).order_by(User.created_at.desc()))
    return result.scalars().all()

async def get_user_with_posts(db:AsyncSession,user_id:int):
    result=await db.execute(select(User).where(User.id==user_id).options(selectinload(User.posts)))
    return result.scalar_one_or_none()

async def count_users(db:AsyncSession)->int:
    result=await db.execute(select(func.count(User.id)))
    return result.scalar()

async def search_users(db:AsyncSession,role:UserRole=None,is_active:bool=None,search:str=None):
    query=select(User)
    conditions=[]

    if role:
        conditions.append(User.role==role)
    if is_active is not None:
        conditions.append(User.is_active==is_active)
    if search:
        conditions.append(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    if conditions:
        query=query.where(and_(*conditions))
    
    result=await db.execute(query)
    return result.scalars().all()

async def update_user_role(db:AsyncSession,user_id:int,new_role:UserRole):
    user=await get_user_by_id(db,user_id)
    if not user:
        return None
    user.role=new_role
    await db.commit()
    await db.refresh(user)
    return user

async def deactivate_all_guests(db:AsyncSession)->int:
    result=await db.execute(update(User).where(User.role==UserRole.GUEST).values(User.is_active==False).returning(User.id))
    await db.commit()
    return len(result.fetchall())

async def delete_user(db:AsyncSession,user_id:int)->bool:
    user=await get_user_by_id(db,user_id)
    if not user:
        return False
    await db.delete(user)
    await db.commit()
    return True

async def delete_inactive_users(db:AsyncSession)->int:
    result=await db.execute(delete(User).where(User.is_active==False).returning(User.id))
    await db.commit()
    return len(result.fetchall())

async def create_user_with_post(db:AsyncSession,username:str,email:str,password:str,post_title:str,post_content:str):
    try:
        user=User(username=username,hashed_password=password,email=email)
        db.add(user)

        # Need user.id for profile's foreign key
        await db.flush()  # ← CRITICAL: gets the ID

        post=Post(title=post_title,content=post_content,author_id=user.id)
        db.add(post)

        # Now both user and profile commit together
        await db.commit()
        await db.refresh(user)
        await db.refresh(post)

        print(f"✅ Created user {user.id} and post {post.id} atomically")
        return user,post
    except Exception as e:
        await db.rollback()
        print(f"❌ Transaction failed, rolled back: {e}")
        raise

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # Drop existing tables
        await conn.run_sync(Base.metadata.create_all)  # Recreate with new schema

    async with AsyncSessionLocal() as db:
        print("\n📝 Testing all CRUD patterns...\n")

        # Create
        user = await create_user(db, "alice", "alice@test.com", "hashed", UserRole.ADMIN)
        print(f"Created: {user}")

        user2 = await create_user(db, "bob", "bob@test.com", "hashed", UserRole.USER)
        print(f"Created: {user2}")

        # Read
        fetched = await get_user_by_id(db, user.id)
        print(f"Fetched by ID: {fetched}")

        all_users = await get_all_users(db)
        print(f"All users: {len(all_users)}")

        count = await count_users(db)
        print(f"Total count: {count}")

        # Search
        admins = await search_users(db, role=UserRole.ADMIN)
        print(f"Admins found: {len(admins)}")

        # Transaction
        user3, post = await create_user_with_post(
            db, "charlie", "charlie@test.com","hashed",
            "My First Post", "Content here"
        )

        # User with posts
        user_with_posts = await get_user_with_posts(db, user3.id)
        print(f"User {user_with_posts.username} has {len(user_with_posts.posts)} posts")

        # Update
        updated = await update_user_role(db, user2.id, UserRole.GUEST)
        print(f"Updated role: {updated.role}")

        # Delete
        deleted = await delete_user(db, user2.id)
        print(f"Deleted: {deleted}")

        print("\n✅ All CRUD patterns work!\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())



        
    









