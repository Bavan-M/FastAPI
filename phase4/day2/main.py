import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from phase4.day1.sqlalchemy_basics_01 import Base
from phase4.day2.database import engine
from phase4.day2.routes import user_router, post_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database ready")
    yield
    await engine.dispose()
    print("✅ Database disposed")


app = FastAPI(
    title="Repository Pattern Demo",
    description="Clean architecture with Repository + Service pattern",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(user_router)
app.include_router(post_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Repository Pattern Demo",
        "endpoints": {
            "users": "/users",
            "posts": "/posts",
            "feed": "/posts/feed"
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)