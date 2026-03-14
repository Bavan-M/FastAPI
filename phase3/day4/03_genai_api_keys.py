import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Depends,HTTPException,status,Security
import secrets
import hashlib
from datetime import datetime
import time
from typing import Optional
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

app=FastAPI(title="Gen AI API Keys")

api_key_header=APIKeyHeader(name="X-API-Key",auto_error=False)

TIERS={
    "free":
    {
        "requests_per_minute":60,
        "requests_per_day":100,
        "max_tokens_per_request":1000,
        "allowed_models":["gpt-3.5-turbo"],
        "allowed_endpoints":["/v1/embeddings"]
    },
    "pro": {
        "requests_per_minute": 60,
        "requests_per_day": 10000,
        "max_tokens_per_request": 4096,
        "allowed_models": ["gpt-3.5-turbo", "gpt-4"],
        "allowed_endpoints": ["/v1/embeddings", "/v1/generate", "/v1/chat"]
    },
    "enterprise": {
        "requests_per_minute": 600,
        "requests_per_day": 1000000,
        "max_tokens_per_request": 128000,
        "allowed_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "claude-3"],
        "allowed_endpoints": ["*"]
    }
}

def make_hash(owner:str,tier:str)->tuple:
    raw="sk-"+secrets.token_urlsafe(32)
    hash=hashlib.sha256(raw.encode()).hexdigest()

    return raw, {
        "owner":owner,
        "tier":tier,
        "active":True,
        "created_at":datetime.now(),
        "total_requests":0,
        "total_tokens":0,
        "requests_today":0,
        "day_reset_at":datetime.now().replace(hour=0,minute=0,second=0),
        "minute_requests":[]
    },hash

api_keys_db={}
hashed_key_index={}

raw_free,free_data,free_hash=make_hash("alice","free")
raw_pro,pro_data,pro_hash=make_hash("bob","pro")
raw_enterprise,enterprise_data,enterprise_hash=make_hash("corp","enterprise")

for raw,data,hash in [(raw_free,free_data,free_hash),(raw_pro,pro_data,pro_hash),(raw_enterprise,enterprise_data,enterprise_hash)]:
    key_id=data['owner']+"_key"
    api_keys_db[key_id]=data
    hashed_key_index[hash]=key_id


print("==="*50)
print(f"free(alice):{raw_free}")
print(f"pro (bob) : {raw_pro}")
print(f"enterprise (corp) : {raw_enterprise}")
print("==="*50)

def check_rate_limit(key_data:dict,endpoint:str,max_tokens:int=0):
    tier=TIERS[key_data["tier"]]
    now=datetime.now()

    if now.date()>key_data['day_reset_at'].date():
        key_data['requests_today']=0
        key_data['day_reset_at']=now

    if key_data['requests_today']>tier['requests_per_day']:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily requests Limit reached {tier['requests_per_day']},Resets at midnight"
        )
    
    one_minute_ago=time.time()-60
    print(one_minute_ago)
    print("***************************")
    print(key_data)
    key_data['minute_requests']=[time for time in key_data['minute_requests'] if time>one_minute_ago]

    if len(key_data['minute_requests'])>tier['requests_per_minute']:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded :{tier['requests_per_minute']} requests/minute for {key_data['tier']}"
        )
    
    allowed=tier['allowed_endpoints']
    if '*' not in allowed and endpoint not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Endpoint '{endpoint}' not available on {key_data['tier']} tier."
        )
    
    if max_tokens>tier['max_tokens_per_request']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"max tokens {max_tokens} exceeds limit of {tier['max_tokens_per_request']} for {key_data['tier']} tier."
        )
    key_data['minute_requests'].append(time.time())
    key_data['requests_today']+=1
    key_data['total_requests']+=1



async def get_api_key_data(api_key:Optional[str]=Security(api_key_header))->dict:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required .Pass it as X-API-Key header"
        )
    
    hashed=hashlib.sha256(api_key.encode()).hexdigest()
    key_id=hashed_key_index.get(hashed)

    if not key_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    

    key_data=api_keys_db.get(key_id)
    if not key_data['active']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key revoked"
        )
    return key_data


class EmbedRequest(BaseModel):
    text:str


@app.post("/v1/embeddings")
async def embeddings(request:EmbedRequest,key_data:dict=Depends(get_api_key_data)):
    check_rate_limit(key_data,"/v1/embeddings")
    fake_tokens=len(request.text.split())*2
    key_data['total_tokens']+=fake_tokens
    return {
        "embeddings":[0.1,0.2,0.3],
        "tokens_used":fake_tokens,
        "tier":key_data['tier']
    }

@app.get("/v1/usage")
async def get_usage(key_data: dict = Depends(get_api_key_data)):
    tier_limits = TIERS[key_data["tier"]]
    return {
        "tier": key_data["tier"],
        "owner": key_data["owner"],
        "usage": {
            "total_requests": key_data["total_requests"],
            "requests_today": key_data["requests_today"],
            "total_tokens": key_data["total_tokens"],
            "requests_this_minute": len(key_data["minute_requests"])
        },
        "limits": {
            "requests_per_minute": tier_limits["requests_per_minute"],
            "requests_per_day": tier_limits["requests_per_day"],
            "max_tokens_per_request": tier_limits["max_tokens_per_request"]
        }
    }