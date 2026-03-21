from pydantic import BaseModel,Field,field_validator
from datetime import datetime
from typing import Optional,List

class RegisterRequest(BaseModel):
    username:str=Field(...,min_length=3,max_length=50)
    email:str=Field(...,pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    password:str=Field(...,min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls,v):
        if not any(c.isupper() for c in v):
            raise ValueError("Passwrod must contain atleast one upper case letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain atleast one digit")
        return v
    
class LoginRequest(BaseModel):
    username:str
    password:str

class LogoutRequest(BaseModel):
    refresh_token:str

class RefreshToken(BaseModel):
    refresh_token:str

class TokenPair(BaseModel):
    access_token:str
    refresh_token:str
    token_type:str="bearer"
    access_expires_in:int
    refresh_expires_in:int

class AccessToken(BaseModel):
    access_token:str
    token_type:str="bearer"
    expires_in:int

class UserResponse(BaseModel):
    username:str
    email:str
    id:int
    role:str
    auth_provider:str
    created_at:datetime

class APIKeyCreate(BaseModel):
    name:str=Field(...,min_length=1,max_length=100)
    expires_in_days:Optional[int]=Field(default=30,ge=1,le=365)
    scopes:List[str]=["read"]
    tier:str=Field(default="free")

    @field_validator("tier")
    @classmethod
    def validate_tier(cls,v):
        if v  not in ["free","pro","enterprise"]:
            raise ValueError("Tier must free,pro or enterprise")
        return v
    

class APIKeyResponse(BaseModel):
    name:str
    id:str
    masked_key:str
    owner:str
    scopes:List[str]
    tier:str
    created_at:datetime
    expires_at:Optional[datetime]
    active:bool
    usage_count:int
    last_used_at:Optional[datetime]


class APICreatedResponse(APIKeyResponse):
    raw_key:str

class UserListResponse(BaseModel):
    total:int
    users:List[UserResponse]

class SystemStats(BaseModel):
    total_users:int
    total_api_keys:int
    active_api_keys:int
    blacklisted_tokens:int
    blocked_accounts:int



        
