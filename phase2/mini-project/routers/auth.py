import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

import time
from fastapi import FastAPI,Depends,BackgroundTasks,APIRouter
from models.schemas import UserResponse,TokenResponse,LoginRequest,RegisterRequest
from data.store import get_user_by_username,create_user
from dependencies.auth import get_current_user
from core.exceptions import ConflictException,UnAuthorizedException
from core.config import settings

router=APIRouter(prefix="/auth",tags=['Auth'])

def send_welcome_email(email:str,username:str):
    time.sleep(1)
    print(f"[EMAIL] Welcome email sent to {email} ,user: {username}")


@router.post("/register",response_model=UserResponse,status_code=201)
def register(request:RegisterRequest,background_task:BackgroundTasks):
    if get_user_by_username(username=request.username):
        raise ConflictException("User","username",request.username)
    
    user=create_user(request.username,request.email,request.password)

    background_task.add_task(send_welcome_email,request.email,request.username)

    return user

@router.get("/login",response_model=TokenResponse)
def login(request:LoginRequest):
    user=get_user_by_username(request.username)
    if not user or user['password']!=request.password:
        raise UnAuthorizedException("Invalid username or password")
    
    token=f"token-{request.username}"
    return {
        "access_token":token,
        "token_type":"bearer",
        "expires_in":settings.token_expire_minutes*60
    }

@router.get("/me",response_model=UserResponse)
def get_me(current_user:dict=Depends(get_current_user)):
    return current_user



