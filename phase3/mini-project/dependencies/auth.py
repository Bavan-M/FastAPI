import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from fastapi.security import OAuth2PasswordBearer
from fastapi import Header,Request,Depends
from core.exceptions import UnAuthorizedException,ForbiddenException
from core.security import decode_access_token,hash_api_key
from data.store import blacklisted_jtis,get_user_by_name,get_api_key_by_hash
from typing import Optional
from datetime import datetime

oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login",auto_error=False)
api_key_header_scheme=Header(None,alias="X-API-Key")

async def get_current_user(request:Request,token:str=Depends(oauth2_scheme))->dict:
    if not token:
        raise UnAuthorizedException("Bearer token required")
    
    payload=decode_access_token(token)
    if not payload:
        raise UnAuthorizedException("Invalid or expired token")
    
    jti=payload.get("jti")
    if jti in blacklisted_jtis:
        raise UnAuthorizedException("User not found")
    
    username=payload.get("sub")
    user=get_user_by_name(username)
    if not user:
        raise UnAuthorizedException("Useer not found")
    
    if user.get("disabled"):
        raise UnAuthorizedException("Account disabled")
    
    request.state.token_payload=payload
    return user
    
def require_roles(*roles:str):
    def depedency(current_user:dict=Depends(get_current_user))->dict:
        if current_user["role"] not in roles:
            raise ForbiddenException(f"Role '{current_user['role']}' not permitted. Required : {list(roles)}")
        return current_user
    return depedency


require_admin=require_roles("admin")

async def get_api_key_data(x_api_key:Optional[str]=Depends(api_key_header_scheme))->dict:
    if not x_api_key:
        raise UnAuthorizedException("X-API Key header required")
    
    hashed=hash_api_key(x_api_key)
    key_data=get_api_key_by_hash(hashed)

    if not key_data:
        raise UnAuthorizedException("Invalid API Key")
    if not key_data["active"]:
        raise UnAuthorizedException("API Key has been revoked")
    
    if key_data["expires_at"] and datetime.now()>key_data["expires_at"]:
        raise UnAuthorizedException("API Key has been expired")
    key_data["usage_count"]=key_data.get("usage_count",0)+1
    key_data["last_used_at"]=datetime.now()

    return key_data
    


    




