import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter,Request,BackgroundTasks,Depends
from datetime import datetime,timedelta
from data.store import locked_accounts,locked_ips,failed_attempts,get_user_by_name,get_user_by_email,create_user,refresh_tokens_store,blacklisted_jtis
from core.exceptions import AccountLockedException,RateLimitException,ConflictException,UnAuthorizedException
from core.config import settings
import time
from models.schemas import UserResponse,RegisterRequest,TokenPair,RefreshToken,AccessToken,LogoutRequest
from fastapi.security import OAuth2PasswordRequestForm
import asyncio
from core.security import verify_password,create_access_token,create_refresh_token,decode_refresh_token
from dependencies.auth import get_current_user

router=APIRouter(prefix="/auth",tags=["Authentication"])

def get_client_ip(request:Request)->str:
    forwarded=request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host

def check_brute_force(username:str,ip:str):
    now=datetime.now()
    if username in locked_accounts:
        if now<locked_accounts[username]:
            remaining=(locked_accounts[username]-now).seconds//60
            raise AccountLockedException(remaining)
        else:
            del locked_accounts[username]

    if ip in locked_ips:
        if now<locked_ips[ip]:
            raise RateLimitException("Too many failed attempts from your IP",60)
        else:
            del locked_ips[ip]

def record_failed_attempt(username:str,ip:str):
    now=datetime.now()
    window=now-timedelta(minutes=10)

    for key in [username,ip]:
        failed_attempts[key]=[time for time in failed_attempts.get(key,[]) if time>window]
        failed_attempts[key].append(now)

        if len(failed_attempts[key])>=settings.max_login_attepmts:
            lock_until=now+timedelta(minutes=settings.lockout_duration_minutes)
            if key==username:
                locked_accounts[key]=lock_until
            elif key==ip:
                locked_ips[key]=lock_until
            print(f"[SECURITY] Locked '{key}' until '{lock_until}'")

def clear_failed_attempts(username:str,ip:str):
    failed_attempts.pop(username,None)
    failed_attempts.pop(ip,None)

def send_welcome_email(username:str,email:str):
    time.sleep(0.5)
    print(f"[EMAIL] Welcome email sent to {email} | username {username}")


@router.post("/register",response_model=UserResponse,status_code=201)
def register(request:RegisterRequest,background_task:BackgroundTasks):
    if get_user_by_name(request.username):
        raise ConflictException(f"Username '{request.username}' already exists")
    if get_user_by_email(request.email):
        raise ConflictException(f"Email {request.email} already registered")
    
    user=create_user(username=request.username,email=request.email,password=request.password)
    background_task.add_task(send_welcome_email,request.username,request.email)
    return user


@router.post("auth/login",response_model=TokenPair)
async def login(request:Request,form_data:OAuth2PasswordRequestForm=Depends()):
    ip=get_client_ip(request)
    username=form_data.username

    check_brute_force(username,ip)

    user=get_user_by_name(username)
    if not user or not verify_password(form_data.password,user['hashed_password']):
        attempt_count=len(failed_attempts.get(username,[]))+1
        await asyncio.sleep(min(attempt_count*0.5,5))
        record_failed_attempt(username,ip)
        raise UnAuthorizedException("Invalid username or password")
    clear_failed_attempts(username,ip)

    token_data={
        "sub":user["username"],
        "role":user["role"],
        "user_id":user["id"]
    }
    access_token=create_access_token(data=token_data)
    refresh_token=create_refresh_token(data=token_data)
    refresh_tokens_store[refresh_token]=user['username']

    return {
        "access_token":access_token,
        "refresh_token":refresh_token,
        "refresh_expires_in":settings.refresh_token_expire_days*24*60*60,
        "access_expires_in":settings.access_token_expire_minutes*60
    }


@router.post("/refresh",response_model=AccessToken)
def refresh(request:RefreshToken):
    payload=decode_refresh_token(request.refresh_token)
    if not payload:
        raise UnAuthorizedException("Invalid or expired refresh token")
    
    if request.refresh_token not in refresh_tokens_store:
        raise UnAuthorizedException("Refresh token revoked")
    username=refresh_tokens_store[request.refresh_token]
    user=get_user_by_name(username)
    if not user:
        raise UnAuthorizedException("User not found")
    
    new_token_data={
        "sub":user['username'],
        "role":user['role'],
        "user_id":user['id']
    }
    new_token=create_access_token(new_token_data)
    return {
        "access_token":new_token,
        "expires_in":settings.access_token_expire_minutes*60
    }

@router.post("/logout")
def logout(req:LogoutRequest,request:Request,current_user:dict=Depends(get_current_user)):
    payload=request.state.token_payload
    blacklisted_jtis.add(payload["jti"])

    refresh_tokens_store.pop(req.refresh_token,None)
    return {
        "message":f"GoodBye {current_user['username']} Loggedout successfully"
    }

@router.get("/me",response_model=UserResponse)
def get_me(current_user:dict=Depends(get_current_user)):
    return current_user










