import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException,Depends,status
from passlib.context import CryptContext
import hashlib
from typing import Optional
from datetime import timedelta,datetime,timezone
from jose import jwt,JWTError 
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm

app=FastAPI(title="JWT auth demo")

SECRET_KEY='super-secret-key-change-in-production'
ALGORITHM='HS256'
ACCESS_TOKEN_EXPIRE_MINUTES=30

pwd_context=CryptContext(schemes='argon2',deprecated='auto')

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)


def verify_password(password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)

def create_access_token(data:dict,expires_delta:Optional[timedelta]=None)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+(expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp":expires})
    return jwt.encode(to_encode,key=SECRET_KEY,algorithm=ALGORITHM)

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


class Token(BaseModel):
    access_token:str
    token_type:str
    expires_in:int

class UserResponse(BaseModel):
    id:int
    username:str
    email:str
    role:str

class RegisterRequest(BaseModel):
    username:str
    email:str
    password:str

oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_users(username:str)->Optional[dict]:
    return fake_db_users.get(username)

def authenticate_user(username:str,password:str)->Optional[dict]:
    user=get_users(username)
    if not user:
        return None
    if not verify_password(password,user['hashed_password']):
        return None
    return user


async def get_current_user(token:str=Depends(oauth2_scheme))->dict:
    credential_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate":"Bearer"}
    )
    try:
        payload=jwt.decode(token,key=SECRET_KEY,algorithms=[ALGORITHM])
        username:str=payload.get('sub')
        if username is None:
            raise credential_exception
    except JWTError:
        raise credential_exception
    
    user=get_users(username)
    if not user:
        raise credential_exception
    return user

async def get_current_active_user(current_user:dict=Depends(get_current_user))->dict:
    if current_user.get('disabled'):
        raise HTTPException(status_code=400,detail="Inactive user")
    return current_user

def require_admin(current_user:dict=Depends(get_current_active_user))->dict:
    if current_user['role']!='admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Admin access required")
    return current_user


@app.post("/auth/register",response_model=UserResponse,status_code=201)
def register(request:RegisterRequest):
    if request.username in fake_db_users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="Username already exists")
    
    new_user={
        "id":len(fake_db_users)+1,
        "username":request.username,
        "email":request.email,
        "hashed_password":hash_password(request.password),
        "role":"user",
        "disabled":False
    }
    fake_db_users[request.username]=new_user
    return new_user


@app.post("/auth/login",response_model=Token)
def login(form_data:OAuth2PasswordRequestForm=Depends()):
    user=authenticate_user(form_data.username,form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Incorrect username and password",  headers={"WWW-Authenticate":"Bearer"})
    access_token=create_access_token(
        data={
            "sub":user['username'],
            "user_id":user['id'],
            "role":user['role']
        }
        ,expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {
        "access_token":access_token,
        "token_type":"bearer",
        "expires_in":ACCESS_TOKEN_EXPIRE_MINUTES*60
    }

@app.get("/auth/me",response_model=UserResponse)
async def get_me(current_user:dict=Depends(get_current_active_user)):
    return current_user

@app.get("/admin/dashboard")
async def admin_dashboard(current_user:dict=Depends(require_admin)):
    return {"message":f"Welcome to admin dashboard {current_user['username']}","total_users":len(fake_db_users)}


