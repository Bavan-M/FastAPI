import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter,HTTPException,Depends
from dependencies.auth import require_admin
from models.schemas import UserListResponse,SystemStats
from data.store import users_db,get_user_by_name,api_keys_db,blacklisted_jtis,locked_accounts

router=APIRouter(prefix="/admin",tags=["Admin"],dependencies=[Depends(require_admin)])

@router.get("/users",response_model=UserListResponse)
def list_all_users():
    users=list(users_db.values())
    return {
        "total":len(users),
        "users":users
    }

@router.patch("/users/{username}/disable")
def disable_user(username:str):
    user=get_user_by_name(username)
    if not user:
        raise HTTPException("User not found",status_code=404)
    user["disabled"]=True
    return {
        "message":f"User {username} disabled"
    }

@router.patch("/users/{username}/enable")
def disable_user(username:str):
    user=get_user_by_name(username)
    if not user:
        raise HTTPException("User not found",status_code=404)
    user["disabled"]=False
    return {
        "message":f"User {username} enabled"
    }

@router.patch("/users/{username}/role")
def change_role(username:str,role:str):
    if role not in ["admin","user","guest"]:
        raise HTTPException(detail="Invalid role",status_code=400)
    user=get_user_by_name(username)
    if not user:
        raise HTTPException(detail="User not found",status_code=404)
    user["role"]=role
    return {
        "message":f"User {username} changed role to {role}"
    }

@router.get("/stats",response_model=SystemStats)
def get_stats():
    return {
        "total_users":len(users_db),
        "total_api_keys":len(api_keys_db),
        "active_api_keys":len([key for key in api_keys_db.values() if key["active"]]),
        "blacklisted_tokens":len(blacklisted_jtis),
        "blocked_accounts":len(locked_accounts)
    }

@router.delete("/users/{username}/unlock")
def unlock_account(username:str):
    locked_accounts.pop(username,None)
    return {"message",f"Account {username} unlocked"}






    
