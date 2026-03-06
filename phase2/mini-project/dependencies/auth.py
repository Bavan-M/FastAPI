import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from fastapi import Header,Depends
from typing import Optional
from data.store import get_user_by_userid
from core.exceptions import UnAuthorizedException,ForbiddenException

ACTIVE_TOKENS={
    "token-alice":1,
    "token-bob":2
}

def get_current_user(authorization:Optional[str]=Header(None))->dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnAuthorizedException("Missing or invalid Authorization header")
    
    token=authorization.split(" ")[1]
    user_id=ACTIVE_TOKENS.get(token)
    if not user_id:
        raise UnAuthorizedException("Invalid or expired tokens")
    
    user=get_user_by_userid(user_id=user_id)
    if not user:
        raise UnAuthorizedException("User no longer exists")
    return user

def require_admin(current_user:dict=Depends(get_current_user))->dict:
    if current_user['role']!='admin':
        raise ForbiddenException("Admin access required")
    return current_user





