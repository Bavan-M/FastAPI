import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter,Depends
from models.schemas import APICreatedResponse,APIKeyCreate,APIKeyResponse
from dependencies.auth import get_current_user
from core.security import generate_api_key,hash_api_key,mask_api_key
import uuid
from datetime import datetime,timedelta
from data.store import store_api_keys,get_api_keys_by_owner,api_keys_db
from core.exceptions import NotFoundExcpetion,ForbiddenException
from typing import List
from fastapi.responses import JSONResponse

router=APIRouter(prefix="/api-keys",tags=["API Keys"])

@router.post("/",response_model=APICreatedResponse,status_code=201)
def create_api_key(request:APIKeyCreate,current_user:dict=Depends(get_current_user)):
    try:
        raw_key=generate_api_key()
        hashed=hash_api_key(raw_key)
        key_id=str(uuid.uuid4())

        expires_at=None
        if request.expires_in_days:
            expires_at=datetime.now()+timedelta(days=request.expires_in_days)

        key_data={
        "name":request.name,
        "id":key_id,
        "masked_key":mask_api_key(raw_key),
        "owner":current_user['username'],
        "scopes":request.scopes,
        "tier":request.tier,
        "created_at":datetime.now(),
        "expires_at":expires_at,
        "active":True,
        "usage_count":0,
        "last_used_at":None
        }

        store_api_keys(key_id,key_data,hashed)
        print(f"[API KEY] Created {request.name} by the username {current_user['username']}")
        return {**key_data,"raw_key":raw_key}
    except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "internal_server_error", "message": str(e)},
            )

@router.get("/",response_model=List[APIKeyResponse])
def list_my_keys(current_user:dict=Depends(get_current_user)):
    try:
        return get_api_keys_by_owner(current_user['username'])
    except Exception as e:
        return JSONResponse(
            content={"message":str(e)}
        )

@router.get("/{key_id}",response_model=APIKeyResponse)
def get_key(key_id:str,current_user:dict=Depends(get_current_user)):
    key=api_keys_db.get(key_id)
    if not key:
        raise NotFoundExcpetion("API Key",key_id)
    if key["owner_id"]!=current_user["id"] and current_user["role"]!="admin":
        raise ForbiddenException("Not youe API key")
    
    return key

@router.delete("/{key_id}")
def revoke_key(key_id:str,current_user:dict=Depends(get_current_user)):
    key=api_keys_db.get(key_id)
    if not key:
        raise NotFoundExcpetion("API Key",key_id)
    if key["owner_id"]!=current_user["id"] and current_user["role"]!="admin":
        raise ForbiddenException("Not your API key")
    key["active"]=False
    print(f"[API KEY] Revoked {key["name"]} by the user {current_user['username']}")
    return {
        "message":f"API KEY {key["name"]} revoked sucessfully"
    }


    


