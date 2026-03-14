import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Depends,HTTPException,status,Security
import hashlib
from passlib.context import CryptContext
from datetime import datetime,timedelta,timezone
from jose import jwt,JWTError
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm,APIKeyHeader
import secrets
from typing import Optional,List
from pydantic import BaseModel
import uuid

app=FastAPI(title="API Key Managment")

SUPER_SECRET_KEY="super-secret-key"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

api_keys_db:dict={}
hashed_key_index:dict={}

pwd_context=CryptContext(schemes="argon2",deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/login")
api_key_header=APIKeyHeader(name="X-API-Key",auto_error=False)

def hash_password(plain_password:str)->str:
    pre_hash=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hash)

def verify_password(password:str,hash_password:str)->bool:
    pre_hash=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hash,hash_password)

def create_access_token(data:dict)->str:
    to_upload=data.copy()
    to_upload["exp"]=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_upload,key=SUPER_SECRET_KEY,algorithm=ALGORITHM)

def generate_api_key()->str:
    return "sk-"+secrets.token_urlsafe(32)

def hash_api_key(api_key:str)->str:
    return hashlib.sha256(api_key.encode()).hexdigest()

def mask_api_key(api_key:str)->str:
    return api_key[:8]+'.....'+api_key[-4:]

async def get_current_user_jwt(token:str=Depends(oauth2_scheme))->dict:
    try:
        payload=jwt.decode(token,key=SUPER_SECRET_KEY,algorithms=[ALGORITHM])
        username=payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid token")
    user=users_db.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="User not found")
    return user


async def get_api_key_owner(api_key:Optional[str]=Security(api_key_header))->dict:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="API Key required")
    
    hashed=hash_api_key(api_key)
    key_id=hashed_key_index.get(hashed)

    if not key_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid api key")
    
    key_data=api_keys_db.get(key_id)
    if not key_data['active']:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="API key revoked")
    
    if key_data['expires_at'] and datetime.now()>key_data['expires_at']:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="API key expired")
    key_data['last_used_at']=datetime.now()
    key_data['usage_count']=key_data.get('usage_count',0)+1
    return key_data

users_db = {
    "alice": {
        "id": 1, "username": "alice",
        "hashed_password": hash_password("pass123"),
        "role": "admin"
    },
    "bob": {
        "id": 2, "username": "bob",
        "hashed_password": hash_password("pass123"),
        "role": "user"
    }
}


class APIKeyCreate(BaseModel):
    name:str
    expires_in_days:Optional[int]=30
    scopes:List[str]=["read"]

class APIKeyResponse(BaseModel):
    id:str
    name:str
    masked_key:str
    owner:str
    scopes:List[str]
    created_at:datetime
    expires_at:Optional[datetime]
    active:bool

class APICreateKeyResponse(APIKeyResponse):
    raw_key:str


@app.post("/auth/login")
async def login(form_data:OAuth2PasswordRequestForm=Depends()):
    user=users_db.get(form_data.username)
    if not user or not verify_password(form_data.password,user['hashed_password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid credentials")
    
    payload={
        "sub":user['username'],
        "role":user['role']
    }
    token=create_access_token(data=payload)
    return {
        "access_token":token,
        "token_type":"Bearer"
    }


@app.post("/api-keys",response_model=APICreateKeyResponse,status_code=status.HTTP_201_CREATED)
async def create_api_key(request:APIKeyCreate,current_user:dict=Depends(get_current_user_jwt)):
    raw_key=generate_api_key()
    hashed=hash_api_key(raw_key)
    key_id=str(uuid.uuid4())

    expires_at=None
    if request.expires_in_days:
        expires_at=datetime.now()+timedelta(days=request.expires_in_days)

    key_data={
        "id":key_id,
        "name":request.name,
        "masked_key":mask_api_key(raw_key),
        "owner":current_user['username'],
        "owner_id":current_user['id'],
        "scopes":request.scopes,
        "created_at":datetime.now(),
        "expires_at":expires_at,
        "active":True,
        "usage_count":0,
        "last_used_at":0
    }

    api_keys_db[key_id]=key_data
    hashed_key_index[hashed]=key_id
    return{
        **key_data,
        "raw_key":raw_key
    }

@app.get("/api-keys",response_model=List[APIKeyResponse])
def list_my_api_keys(current_user:dict=Depends(get_current_user_jwt)):
    my_apis=[key for key in api_keys_db.values() if key['owner_id']==current_user['id']]
    return my_apis

@app.get("/api-keys/{key_id}",response_model=APIKeyResponse)
def get_api_key_details(key_id:str,current_user:dict=Depends(get_current_user_jwt)):
    key=api_keys_db.get(key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="API Key not found")
    
    if key['owner_id']!=current_user['id'] and current_user['role']!="admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Not your API key")
    return key

@app.delete("/api-keys/{key_id}",response_model=APIKeyResponse)
def revoke_api_key(key_id:str,current_user:dict=Depends(get_current_user_jwt)):
    key=api_keys_db.get(key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="API Key not found")
    
    if key['owner_id']!=current_user['id'] and current_user['role']!="admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Not your API key")
    key['active']=False
    print(f"[API KEY] Revoked '{key['name']}' for {current_user['username']}")
    return {
        "message":f"API key '{key['name']}' revoked successfully"
    }

@app.post("/v1/embeddings")
async def create_embeddings(text:str,key_data:dict=Depends(get_api_key_owner)):
    if "embeddings" not in key_data['scopes'] and "admin" not in key_data['scopes']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Key missing 'embedding' scope")
    return {
        "text":text,
        "embeddings":[0.1,0.2,0.3],
        "usage_count":key_data['usage_count'],
        "key_name":key_data['name']
    }

@app.post("/ai/generate")
async def generate(text:str,key_data:dict=Depends(get_api_key_owner)):
    if "generate" not in key_data['scopes'] and "admin" not in key_data['scopes']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Key missing 'generate' scope")
    return {
        "prompt":text,
        "response":f"Response for {text}.............",
        "key_owner":key_data['name']
    }
