import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException,Depends,status
from passlib.context import CryptContext
from datetime import datetime,timezone,timedelta
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
import hashlib
from jose import jwt,JWTError
from typing import Optional
from pydantic import BaseModel

app=FastAPI(title="Refresh tokens demo")

SECRET_KEY="your-super-secret-key-change-in production"
REFRESH_SECRET_KEY="your-refresh-access-token-different-from access-token"
ALGORITHM='HS256'
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

refresh_token_store:dict={}


pwd_context=CryptContext(schemes='argon2',deprecated='auto')
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)


fake_db_users={
    "alice":{
        "id":1,
        "username":"alice",
        "email":"alice@gmail.com",
        "hashed_password":hash_password("password@123"),
        "role":"admin",
        "disabled":False
    },
    "bob":{
        "id":2,
        "username":"bob",
        "email":"bob@gmail.com",
        "hashed_password":hash_password("password@456"),
        "role":"user",
        "disabled":False
    }
}

def create_access_token(data:dict)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp":expires,"type":"access"})
    return jwt.encode(to_encode,key=SECRET_KEY,algorithm=ALGORITHM)


def create_refresh_token(data:dict)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp":expires,"type":"refresh"})
    return jwt.encode(to_encode,key=REFRESH_SECRET_KEY,algorithm=ALGORITHM)

def decode_access_token(token:str)->Optional[dict]:
    try:
        payload=jwt.decode(token=token,key=SECRET_KEY,algorithms=ALGORITHM)
        if payload['type']!='access':
            return None
        return payload
    except JWTError:
        return None
    

def decode_refresh_token(token:str)->Optional[dict]:
    try:
        payload=jwt.decode(token=token,key=REFRESH_SECRET_KEY,algorithms=ALGORITHM)
        if payload['type']!='refresh':
            return None
        return payload
    except JWTError:
        return None
    
async def get_current_user(token:str=Depends(oauth2_scheme))->dict:
    credential_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate":"Bearer"}
    )
    payload=decode_access_token(token=token)
    if not payload:
        raise credential_exception
    
    username=payload.get('sub')
    user=fake_db_users.get(username)
    if not user:
        raise credential_exception
    return user


class TokenPair(BaseModel):
    access_token:str
    refresh_access_token:str
    token_type:str="bearer"
    access_expires_in:int=ACCESS_TOKEN_EXPIRE_MINUTES*60
    refresh_access_expires_in:int=REFRESH_TOKEN_EXPIRE_DAYS*24*60*60

class AccessTokenResponse(BaseModel):
    access_token:str
    token_type:str='bearer'
    expires_in:int=ACCESS_TOKEN_EXPIRE_MINUTES*60

class RefreshRequest(BaseModel):
    refresh_token:str



@app.post("/auth/login",response_model=TokenPair)
def login(form_data:OAuth2PasswordRequestForm=Depends()):
    user=fake_db_users.get(form_data.username)
    if not user or not verify_password(form_data.password,user['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    token_data={"sub":user['username'],"role":user['role']}

    access_token=create_access_token(data=token_data)
    refresh_access_token=create_refresh_token(data=token_data)

    refresh_token_store[refresh_access_token]=user['username']
    print(refresh_token_store)
    return {
        "access_token":access_token,
        "refresh_access_token":refresh_access_token
    }


@app.post("/auth/refresh",response_model=AccessTokenResponse)
def refresh_access_token(request:RefreshRequest):
    payload=decode_refresh_token(token=request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    username=refresh_token_store.get(request.refresh_token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )
    user=fake_db_users.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="user not found")
    
    new_access_token={"sub":user['username'],"role":user['role']}
    token=create_access_token(data=new_access_token)
    return {
        "access_token":token,
        "expires_in":ACCESS_TOKEN_EXPIRE_MINUTES
    }

@app.post("/auth/logout")
def logout(request:RefreshRequest,current_user:dict=Depends(get_current_user)):
    if request.refresh_token in refresh_token_store:
        del refresh_token_store[request.refresh_token]
        return {"message":f"{current_user['username']} logged out successfully!"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invlaid refresh token ")



    


