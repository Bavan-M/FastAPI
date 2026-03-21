import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from passlib.context import CryptContext
import hashlib
from datetime import datetime,timedelta,timezone
from core.config import settings
import uuid
from jose import jwt,JWTError
import secrets

pwd_context=CryptContext(schemes=["argon2"],deprecated="auto")

def hash_password(plain_password:str)->str:
    pre_hash=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hash)

def verify_password(password:str,hashed_password:str)->bool:
    pre_hash=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hash,hashed_password)

def create_access_token(data:dict)->str:
    to_encode=data.copy()
    to_encode.update({
        "exp":datetime.now(timezone.utc)+timedelta(minutes=settings.access_token_expire_minutes),
        "type":"access",
        "jti":str(uuid.uuid4())
    })
    return jwt.encode(to_encode,key=settings.secret_key,algorithm=settings.algorithm)

def create_refresh_token(data:dict)->str:
    to_encode=data.copy()
    to_encode.update({
        "exp":datetime.now(timezone.utc)+timedelta(days=settings.refresh_token_expire_days),
        "type":"refresh",
        "jti":str(uuid.uuid4())
    })
    return jwt.encode(to_encode,key=settings.refresh_secret_key,algorithm=settings.algorithm)

def decode_access_token(token:str)->dict:
    try:
        payload=jwt.decode(token,key=settings.secret_key,algorithms=[settings.algorithm])
        if payload.get("type")!="access":
            return None
        return payload
    except JWTError:
        return None
    
def decode_refresh_token(token:str)->dict:
    try:
        payload=jwt.decode(token,key=settings.refresh_secret_key,algorithms=[settings.algorithm])
        if payload.get("type")!="refresh":
            return None
        return payload
    except JWTError:
        return None
    
def generate_api_key()->str:
    return "sk-"+secrets.token_urlsafe(32)

def hash_api_key(key:str)->str:
    return hashlib.sha256(key.encode()).hexdigest()

def mask_api_key(key:str)->str:
    return key[:8]+"..."+key[-4:]

