import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from pydantic import BaseModel,Field
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from fastapi.exceptions import RequestValidationError

app=FastAPI()

class LLMRequest(BaseModel):
    prompt:str=Field(...,min_length=1,max_length=1000)
    temperature:float=Field(default=0.7,ge=0.3,le=1)
    max_tokens:int=Field(default=512,ge=0,le=4096)

@app.get("/defualt-vaidation")
def default_validation(request:LLMRequest):
    return{"recieved":request.model_dump()}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request:Request,exc:RequestValidationError):
    errors=[]
    for error in exc.errors():
        errors.append(
            {
                "field": "->".join(str(loc) for loc in error['loc']),
                "issue": error['msg'],
                "invalid_issue": error.get('input') 
            }
        )
    return JSONResponse(status_code=422,content={
        "error":"validation_error",
        "message":"Invalid request data",
        "details":errors
    })

@app.post("/llm/generate")
def generate(request:LLMRequest):
    return {"prompt":request.prompt,"config":request.model_dump()}