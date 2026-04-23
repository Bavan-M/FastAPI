from datetime import datetime,timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from app.models import (
    UserCreate, UserResponse,
    GenerateRequest, GenerateResponse,
    ItemCreate, ItemResponse
)
from app.dependencies import (
    get_current_user, require_admin,
    get_llm_service, users_db,
    items_db, item_counter
)

router = APIRouter()


# --- Auth ---
@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(data: UserCreate):
    # Check duplicate username
    existing = [u for u in users_db.values()
                if u["username"] == data.username]
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    new_id = len(users_db) + 1
    user = {
        "id":         new_id,
        "username":   data.username,
        "email":      data.email,
        "role":       "user",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    users_db[f"token-{data.username}"] = user
    return user


@router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return {**current_user, "created_at": datetime.now(timezone.utc).isoformat()}


# --- LLM ---
@router.post("/llm/generate", response_model=GenerateResponse)
async def generate(
    request:     Request,
    req:         GenerateRequest,
    current_user: dict = Depends(get_current_user),
    llm:         object = Depends(get_llm_service)
):
    try:
        request_id = getattr(request.state, "request_id", "test")

        result = await llm.generate(req.prompt, req.model, req.max_tokens)

        return {
            "prompt":      req.prompt,
            "response":    result["response"],
            "model":       result["model"],
            "tokens_used": result["tokens_used"],
            "request_id":  request_id
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail="LLM service temporarily unavailable")


@router.get("/llm/status")
async def llm_status(llm: object = Depends(get_llm_service)):
    available = await llm.is_available()
    return {"available": available, "model": "gpt-4"}


# --- Items ---
@router.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(
    item:         ItemCreate,
    current_user: dict = Depends(get_current_user)
):
    global item_counter
    new_item = {
        "id":          item_counter,
        "title":       item.title,
        "description": item.description,
        "price":       item.price,
        "owner_id":    current_user["id"],
        "created_at":  datetime.now(timezone.utc).isoformat()
    }
    items_db[item_counter] = new_item
    item_counter += 1
    return new_item


@router.get("/items", response_model=List[ItemResponse])
async def list_items(current_user: dict = Depends(get_current_user)):
    user_items = [
        i for i in items_db.values()
        if i["owner_id"] == current_user["id"]
    ]
    return user_items


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id:      int,
    current_user: dict = Depends(get_current_user)
):
    item = items_db.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["owner_id"] != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not your item")
    return item


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id:      int,
    current_user: dict = Depends(get_current_user)
):
    item = items_db.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["owner_id"] != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not your item")
    del items_db[item_id]


# --- Admin ---
@router.get("/admin/users", dependencies=[Depends(require_admin)])
async def list_all_users():
    return {"users": list(users_db.values())}