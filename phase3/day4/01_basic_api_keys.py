import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException,status,Security
from datetime import datetime,timedelta,timezone
from fastapi.security import APIKeyHeader,APIKeyQuery
import secrets
import hashlib
from typing import Optional


app=FastAPI(title="Basic api key demo")


api_key_header=APIKeyHeader(name="X-API-Key",auto_error=False)
api_key_query=APIKeyQuery(name="api_key",auto_error=False)

def generate_api_key()->str:
    return "sk-"+secrets.token_urlsafe(32)

def hash_api_key(api_key:str)->str:
    return hashlib.sha256(api_key.encode()).hexdigest()

api_keys_db={}

_test_keys={}
for username in ["alice","bob","service_account"]:
    raw_key=generate_api_key()
    hashed=hash_api_key(raw_key)
    api_keys_db[hashed]={
        "owner":username,
        "created_at":datetime.now(),
        "active":True
    }

    _test_keys[username]=raw_key
print("testing api keys")
for owner,key in _test_keys.items():
    print(f"{owner}:{key}")
print("=" * 50 + "\n")

async def get_api_key(header_key:Optional[str]=Security(api_key_header),query_key:Optional[str]=Security(api_key_query))->dict:
    api_key=header_key or query_key
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="API key required. Pass it as X-API-Key header or api_key query param")
    hashed=hash_api_key(api_key)
    key_data=api_keys_db.get(hashed)

    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid api key"
        )
    if not key_data['active']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked"
        )
    
    return key_data


@app.get("/")
def public_route():
    return {
        "meesage":"Public no API key needed"
    }

@app.get("/protected")
async def protected(key_data:dict=Security(get_api_key)):
    return {
        "meesage":"Access granted",
        "owner":key_data['owner'],
        "key_created":key_data['created_at']
    }

@app.post("/ai/embed")
async def embed(text:str,key_data:dict=Security(get_api_key)):
    return {
        "text":text,
        "embeddings":[0.1,0.2,0.3],
        "requested_by":key_data['owner']
    }