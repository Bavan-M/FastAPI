import os
import asyncio
from fastapi import APIRouter,HTTPException,Depends
from pydantic import BaseModel
from app.dependencies import get_current_user,require_admin

router=APIRouter(prefix="/api/v1")

class GenerateRequest(BaseModel):
    prompt:str

@router.get("/items")
async def get_items():
    await asyncio.sleep(0.1)
    return {"items":[{"item":i,"name":f"item{i}"} for i in range(5)]}

@router.post("/generate")
async def generate(req: GenerateRequest,current_user:dict=Depends(get_current_user)):
    await asyncio.sleep(0.5)
    return {
        "response":   f"Response to: {req.prompt[:30]}",
        "model":      os.getenv("DEFAULT_MODEL", "gpt-4"),
        "container":  os.getenv("HOSTNAME", "local"),
        "user":current_user["username"]
    }


@router.get("/info")
def info():
    return {
        "app":         os.getenv("APP_NAME", "Gen AI API"),
        "version":     os.getenv("VERSION", "1.0.0"),
        "environment": os.getenv("ENV", "production"),
        "container":   os.getenv("HOSTNAME", "local")
    }


@router.get("/admin/stats")
async def admin_stats(
    admin_user: dict = Depends(require_admin)  # ← Requires admin role
):
    """
    Only admin users can access this.
    """
    return {
        "total_requests": 1000,
        "active_users": 42,
        "admin": admin_user["username"]
    }