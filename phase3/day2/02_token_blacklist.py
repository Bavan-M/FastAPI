import sys,os
sys.path.insert(0,os.path.dirname(__file__))
from fastapi import FastAPI,Request,Depends,HTTPException,status
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
import hashlib
from jose import jwt,JWTError
import uuid
from datetime import datetime,timedelta,timezone
from typing import Set
from pydantic import BaseModel

SECRET_KEY="your-super-secret-key"
REFRESH_SECRET_KEY="your-refresh-secret-key"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

app=FastAPI(title="Token Blacklist demo")

pwd_context=CryptContext(schemes="argon2",deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(passowrd:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(passowrd.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)

fake_db_user={
    "alice":{
        "id":1,
        "username":"alice",
        "email":"alice@gmail.com",
        "password":hash_password("password@123"),
        "role":"admin"
    }
}


def create_access_token(data:dict)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp":expires,"type":"access","jti":str(uuid.uuid4())})
    return jwt.encode(to_encode,key=SECRET_KEY,algorithm=ALGORITHM)

def create_refresh_token(data:dict)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp":expires,"type":"refresh","jti":str(uuid.uuid4())})
    return jwt.encode(to_encode,key=REFRESH_SECRET_KEY,algorithm=ALGORITHM)

# Store blacklisted JTI (JWT ID) values
# JTI = unique identifier for each token

blacklisted_tokens:Set[str]=set()

def is_blacklisted(jti:str)->bool:
    return jti in blacklisted_tokens

def blacklist_token(jti:str):
    blacklisted_tokens.add(jti)
    print(f"[BLACLKLISTED] token {jti[:8]}...... is blacklisted")

async def get_currect_user(request:Request,token:str=Depends(oauth2_scheme))->dict:
    credential_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate":"Bearer"}
    )
    try:
        payload=jwt.decode(token=token,key=SECRET_KEY,algorithms=[ALGORITHM])
        if payload['type']!="access":
            raise credential_exception
    
        jti=payload.get('jti')
        if not jti or is_blacklisted(jti):
            raise HTTPException(
                tatus_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        username=payload.get('sub')
        if not username:
            raise credential_exception
    except JWTError:
        raise credential_exception
    
    user=fake_db_user.get(username)
    if not user:
        raise credential_exception
    
    request.state.token_payload=payload # Store token payload in request state for logout use
    return user

refresh_access_store:dict={}
    
class TokenPair(BaseModel):
    access_token:str
    refresh_token:str
    token_type:str="bearer"

class LogoutRequest(BaseModel):
    refresh_token:str



@app.post("/auth/login",response_model=TokenPair)
async def login(form_data:OAuth2PasswordRequestForm=Depends()):
    user=fake_db_user.get(form_data.username)
    if not user or not verify_password(form_data.password,user['password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid credentials")
    
    token_data={"sub":user['username'],"role":user['role']}
    access_token=create_access_token(data=token_data)
    refresh_token=create_refresh_token(data=token_data)

    refresh_access_store[refresh_token]=user['username']
    return {"access_token":access_token,"refresh_token":refresh_token}


@app.post("/auth/logout")
async def logout(req:LogoutRequest,request:Request,current_user:dict=Depends(get_currect_user)):
    token_payload=request.state.token_payload
    blacklist_token(token_payload['jti'])

    if req.refresh_token in refresh_access_store:
        del refresh_access_store[req.refresh_token]

    try:
        refresh_paylod= jwt.decode(req.refresh_token,key=REFRESH_SECRET_KEY,algorithms=[ALGORITHM])
        blacklist_token(refresh_paylod['jti'])
    except JWTError:
        pass
    return {"message":f"{current_user['username']} Logged out succesfully,Both access tokens revoked"}




    






