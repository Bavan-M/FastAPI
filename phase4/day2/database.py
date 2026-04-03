import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from dotenv import load_dotenv

load_dotenv("phase4/.env")


DATABASE_URL=os.getenv("DATABASE_URL","postgresql+asyncpg://postgres:master@localhost:5432/fastapi_phase4")
engine=create_async_engine(url=DATABASE_URL,echo=False)
AsyncSessionLocal=AsyncSession(bind=engine,expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            