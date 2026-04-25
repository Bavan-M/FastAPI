import os,sys
from fastapi import APIRouter,FastAPI
import time
from pydantic import BaseModel
import asyncio

router=APIRouter()


class GenerateRequest(BaseModel):
    prompt:str

@router.get("/health")
def health():
    return {
        "status":"ok",
        "env":os.getenv("ENV","production")
    }

@router.get("/ready")
def ready():
    return {
        "status":"ready"
    }

@router.post("/generate")
async def generate(req:GenerateRequest):
    await asyncio.sleep(0.5)
    return {
        "response":f"Response to {req.prompt[:20]}",
        "model":os.getenv("DEFAULT_MODEL","gpt-4o"),
        "container":os.getenv("HOSTNAME","local")
    }

@router.get("/info")
def info():
    return {
        "app":os.getenv("APP_NAME","Gen AI App"),
        "version":os.getenv("VERSION","1.0.0"),
        "environment":os.getenv("ENV","production"),
        "python":os.popen("python --version").read().strip(),
        "container_id":os.getenv("HOSTNAME","local")
    }