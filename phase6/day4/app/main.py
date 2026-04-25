import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes import router

@asynccontextmanager
async def lifespan(app:FastAPI):
    print(f"🚀 Starting {os.getenv('APP_NAME', 'Gen AI API')}")
    print(f"   Environment: {os.getenv('ENV', 'production')}")
    print(f"   Workers:     {os.getenv('WORKERS', '1')}")
    yield
    print("🛑 Shutting down...")

def create_app()->FastAPI:
    app=FastAPI(
        title=os.getenv("APP_NAME","Gen AI App"),
        version=os.getenv("VERSION","1.0.0"),
        lifespan=lifespan
    )
    app.include_router(router)
    return app

app=create_app()
