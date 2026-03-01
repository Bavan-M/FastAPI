from pydantic import BaseModel,Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    '''UserBase is used for output (returning user data)'''
    username:str
    email:str

class UserCreate(UserBase):
    '''UserCreate is only used for input (creating/registering)'''
    password:str

class UserResponse(UserBase):
    '''UserResponse returns id,username,email and cretaed_at but not password'''
    id:int
    created_at:datetime=Field(default_factory=datetime.now)

    class Config:
        from_attributes=True

class DocumentBase(BaseModel):
    '''Document always requires title and content'''
    title:str
    content:str

class DocumentCreate(DocumentBase):
    '''Document create needs title ,content and category as optional'''
    category:Optional[str]=None

class DocumentResponse(DocumentBase):
    '''Document response will have id,title,content,category as optional ,created by and created at'''
    id:int
    category:Optional[str]=None
    created_by:str
    created_at:datetime=Field(default_factory=datetime.now)

class LMMRequest(BaseModel):
    '''LLM requires prompt,model name,temperature,max_tokens and stream'''
    prompt:str=Field(...,min_length=1,max_length=4000)
    model:str="gpt-4"
    temperature:float=Field(default=0.7,ge=0.2,le=2.0)
    max_tokens:int=Field(default=512,ge=1,le=4096)
    stream:bool=False

class LLMResponse(BaseModel):
    '''LLM response will have prompt just to match to the response of the llm,response ,model name and tokens used'''
    prompt:str
    response:str
    model:str
    tokens_used:int








