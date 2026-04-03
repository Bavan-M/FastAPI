import os,sys
sys.path.insert(0,os.path.dirname(__file__))
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession,async_sessionmaker
from typing import AsyncGenerator

from sqlalchemy_basics_01 import Base, User, Posts, Tag, APIKey, UseRole, PostStatus
from dotenv import load_dotenv
from sqlalchemy import text,select
load_dotenv("phase4/.env")

DATABASE_URL=os.getenv("DATABASE_URL")

engine=create_async_engine(
    url=DATABASE_URL,
    pool_size=10, ## keep 10 connections open
    max_overflow=20,  # allow 20 extra connections at peak
    pool_pre_ping=True, # verify connections before using them
    pool_recycle=3600, # recycle connections after 1 hour
    echo=True # log all SQL — disable in production
)

# You create an engine (kitchen) once. You create a sessionmaker (waiter factory) once, configured with your preferences. 
# Then for each incoming request, you call AsyncSessionLocal() to get a fresh session (waiter) that:
# Knows which kitchen to use
# Works asynchronously
# Keeps objects usable after commits
# Doesn't auto-commit anything
# Doesn't auto-flush anything
# This gives you maximum control. You decide when to commit, when to flush, and whether objects should remain accessible after transactions. 
# The trade-off is you must explicitly manage these operations rather than relying on automatic behavior.
AsyncSessionLocal=async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# The Request Lifecycle
# When a request comes in:
# The database session is created
# The session is given to your endpoint
# Your endpoint does its work using this session
# If all goes well, changes are automatically committed
# If anything fails, changes are automatically rolled back
# The session is automatically closed
# An async generator is the same concept, but while waiting for the next item, the delivery person can go serve other customers. They're not blocked waiting for your dessert to be ready—they handle other deliveries in between.
# In the context of your database dependency, yield session gives the session to your endpoint and then pauses. The function doesn't continue until after your endpoint finishes. This pause is what allows the cleanup code (commit or rollback) to run after your endpoint is done.
async def get_db()->AsyncGenerator[AsyncSession,None]:
    """FastAPI that provides a DB session.
    Automatically commits on success ,rolls back to error"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception :
            await session.rollback()
            raise

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created")

async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("All tables dropped")

async def test_connection():
    async with engine.connect() as conn:
        result=await conn.execute(text("SELECT version()"))
        version=result.scalar()
        print(f"Connected to PostgreSQL : {version[:40]}")


async def test_crud():
    async with AsyncSessionLocal() as session:
        # --- CREATE ---
        # user=User(username="alice",
        #           email="alice@gmail.com",
        #           hashed_password="hashed_password_here",
        #           role=UseRole.ADMIN)
        
        # session.add(user)
        # await session.commit()
        # await session.refresh(user)
        # print(f"Created : {user}")

        # --- READ ---
        result=await session.execute(select(User).where(User.username=="alice"))
        fetched_user= result.scalar_one_or_none()
        print(f"Fetched : {fetched_user}")

        # --- UPDATE ---
        fetched_user.role=UseRole.USER
        await session.commit()
        print(f"Updated role :{fetched_user.role}")

        # await session.delete(fetched_user)
        # await session.commit()
        # print("Deleted user")

        # --- VERIFY ---
        result=session.execute(select(User).where(User.username=="alice"))
        gone=await result.scalar_onr_or_none()
        print(f"User exixts after delete : {gone}")






    
async def main():
    print("Testing sqlalchemy")
    await test_connection()
    await create_tables()
    await test_crud()

if __name__=="__main__":
    asyncio.run(main=main())


