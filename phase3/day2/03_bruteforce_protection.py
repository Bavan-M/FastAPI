import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Request,Depends,HTTPException,status
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
from passlib.context import CryptContext
import hashlib
from jose import jwt
from datetime import datetime,timezone,timedelta
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict
import asyncio


app=FastAPI(title="Brute force protection Demo")

SECRET_KEY="super-secret-key-change-in-production"
ACCESS_TOKEN_EXPIRE_IN_MINUTES=15
ALGORITHM="HS256"

MAX_ATTEMPT=5 # lock after 5 failed attempts
LOCKOUT_DURATION_MINUTES=15 # locked for 15 minutes
ATTEMPT_WINDOW_MINUTES=10 # count attempts within 10 minutes

pwd_context=CryptContext(schemes="argon2",deprecated="auto")

locked_ips:dict={} # { ip: locked_until_datetime }
locked_accounts:dict={} # { username: locked_until_datetime }   
failed_attempts:dict=defaultdict(list) 

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(password:str,hash_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hash_password)


def create_access_token(data:dict)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_IN_MINUTES)
    to_encode.update({"exp":expires})
    return jwt.encode(to_encode,key=SECRET_KEY,algorithm=ALGORITHM)


def get_client_ip(request:Request)->str:
    forwarded=request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


def is_locked(key:str,lock_store:dict)->Optional[datetime]:
    if key in lock_store:
        locked_until=lock_store[key]
        if datetime.now()<locked_until:
            return locked_until
        else:
            del lock_store[key]
    return None

fake_user_db={
    "alice":
    {
        "id":1,
        "username":"alice",
        "password":hash_password("password@123"),
        "email":"alice@gmail.com",
        "role":"admin"
    },
    "bob":
    {
        "id":2,
        "username":"bob",
        "password":hash_password("password@456"),
        "email":"bob@gmail.com",
        "role":"user"
    }
}

class Token(BaseModel):
    access_token:str
    token_type:str="Bearer"

def record_failed_attempt(key:str):
    now=datetime.now()
    window_start=now-timedelta(minutes=ATTEMPT_WINDOW_MINUTES)

    failed_attempts[key]=[t for t in failed_attempts[key] if t>window_start]

    failed_attempts[key].append(now)
    attempt_count=len(failed_attempts[key])

    print(f"[SECURITY] Failed attempts {attempt_count} for the key {key}")

    if attempt_count>MAX_ATTEMPT:
        locked_until=now+timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        return locked_until,attempt_count
    return None,attempt_count

def clear_failed_attempt(key:str):
    if key in failed_attempts:
        del failed_attempts[key]


@app.post("/auth/login",response_model=Token)
async def login(request:Request,form_data:OAuth2PasswordRequestForm=Depends()):
    username=form_data.username
    ip=get_client_ip(request)
    ip_locked_until=is_locked(ip,locked_ips)
    if ip_locked_until:
        remaining=(ip_locked_until-datetime.now()).seconds//60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts from your IP.Please try again after {remaining}"
        )
    
    accounts_locked_until=is_locked(username,locked_accounts)
    if accounts_locked_until:
        remaining=(accounts_locked_until-datetime.now()).seconds//60
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked due to too many requests .Try again after {remaining}"
        )
    

    user=fake_user_db.get(username)
    valid=user and verify_password(form_data.password,user['password'])
    if not valid:
        attempt_count=len(failed_attempts.get(username,[]))+1
        delay=min(attempt_count*0.5,5.0)
        await asyncio.sleep(delay)

        locked_until_ips,ip_count=record_failed_attempt(ip)
        locked_until_username,user_count=record_failed_attempt(username)

        if locked_until_ips:
            locked_ips[ip]=locked_until_ips
            print(f"[SECURITY] ip {ip} locked until {locked_until_ips}")
        
        if locked_until_username:
            locked_accounts[username]=locked_until_username
            print(f"[SECURITY] Account: {username} locked until {locked_until_username}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    clear_failed_attempt(key=ip)
    clear_failed_attempt(key=username)

    print(f"Security login success for {username} on {ip}")

    data={
        "sub":user['username'],
        "role":user['role']
    }
    access_token=create_access_token(data)
    return {
        "access_token":access_token
    }


    

