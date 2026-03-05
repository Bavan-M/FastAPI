from pydantic import BaseModel,Field
from typing import Optional,Literal
from datetime import datetime

class RegisterRequest(BaseModel):
    username:str=Field(...,min_length=3,max_length=20)
    email:str=Field(...,pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    password:str=Field(...,max_length=10)


class LoginRequest(BaseModel):
    username:str
    password:str

class TokenResponse(BaseModel):
    access_token:str
    token_type:str="bearer"
    expires_in:int

class UserResponse(BaseModel):
    id:int
    username:str
    email:str
    role:str
    create_at:datetime

class TaskCreate(BaseModel):
    title:str=Field(...,min_length=1,max_length=200)
    description:Optional[str]=Field(None,max_length=1000)
    priority:Literal['low','medium','high']='medium'


class TaskUpdate(BaseModel):
    title:Optional[str]=Field(None,min_length=1,max_length=200)
    description:Optional[str]=None
    status:Optional[Literal['todo','in_progress','done']]=None
    priority:Optional[Literal['low','medium','high']]=None

class TaskResponse(BaseModel):
    title:str
    description:Optional[str]
    status:str
    priority:str
    owner_id:int
    created_at:datetime

class MessageResponse(BaseModel):
    message:str

class ErrorMessage(BaseModel):
    error:str
    message:str
    details:Optional[dict]={}

     