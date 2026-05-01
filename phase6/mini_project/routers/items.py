import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from models.schemas import ItemCreate, ItemResponse
from routers.auth import get_current_user
from core.logging import db_logger

router  = APIRouter(prefix="/items", tags=["Items"])
items_db: dict = {}
counter = 1


@router.get("", response_model=List[ItemResponse])
async def list_items(current_user: dict = Depends(get_current_user)):
    await asyncio.sleep(0.05)   # simulate DB query
    return [i for i in items_db.values()
            if i["owner_id"] == current_user["id"]]


@router.post("", response_model=ItemResponse, status_code=201)
async def create_item(
    item:         ItemCreate,
    request:      Request,
    current_user: dict = Depends(get_current_user)
):
    global counter
    new_item = {
        "id":          counter,
        "title":       item.title,
        "description": item.description,
        "price":       item.price,
        "owner_id":    current_user["id"],
        "created_at":  datetime.utcnow()
    }
    items_db[counter] = new_item
    counter += 1

    db_logger.bind(
        request_id=getattr(request.state, "request_id", ""),
        item_id=   new_item["id"],
        user=      current_user["username"]
    ).info("Item created")

    return new_item


@router.get("/{item_id}", response_model=ItemResponse)
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


@router.delete("/{item_id}", status_code=204)
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