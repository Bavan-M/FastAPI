import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from fastapi import FastAPI,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,Field
from fastapi.responses import JSONResponse
import uuid

app=FastAPI()

class AppException(Exception):
    def __init__(self,status_code:int,error:str,message:str,details:dict=None):
        self.status_code=status_code
        self.error=error
        self.message=message
        self.details=details or {}

class NotFoundException(AppException):
    def __init__(self, resource:str,id:int):
        super().__init__(
            status_code=404, 
            error="not found", 
            message=f"{resource} with id {id} not found", 
            details={"resource":resource,"id":id}
        )

class UnAuthorizedException(AppException):
    def __init__(self, message:str="Authentication required"):
        super().__init__(
            status_code=401, 
            error="unauthorized", 
            message=message
        )
class LLMServiceException(AppException):
    def __init__(self, provider:str,reason:str):
        super().__init__(
            status_code=503, 
            error="llm_service_unavaliable", 
            message=f"{provider} is currently unavialable", 
            details={"provider":provider,"reason":reason}
        )

def error_reponse(status_code:int,error:str,message:str,details:dict=None,request_id:str=None):
    return JSONResponse(
        status_code=status_code,
        content=
        {
            "message":message,
            "error":error,
            "details":details or {},
            "request_id":request_id or str(uuid.uuid4())
        }
    )

@app.exception_handler(AppException)
async def app_exception_handler(request:Request,exc:AppException):
    request_id=getattr(request.state,"request_id",str(uuid.uuid4()))
    return error_reponse(
        status_code=exc.status_code,
        error=exc.error,
        message=exc.message,
        details=exc.details,
        request_id=request_id
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request:Request,exc:HTTPException):
    request_id=getattr(request.state,"request_id",str(uuid.uuid4()))
    return error_reponse(
        status_code=exc.status_code,
        error="http_error",
        details=exc.details,
        request_id=request_id
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request:Request,exc:RequestValidationError):
    request_id=getattr(request.state,"reques_id",str(uuid.uuid4()))
    errors=[
        {
            "field":"->".join(loc for loc in error['loc']),
            "issue":error['msg'],
            "invalid_value":error.get('invalid')
        }
        for error in exc.errors()
    ]
    return error_reponse(
        status_code=422,
        error="validation_error",
        message="Invalid request data",
        details={"errors":errors},
        request_id=request_id
    )

@app.exception_handler(Exception)
async def unhandled_excpetion_handler(request:Request,exc:RequestValidationError):
    request_id=getattr(request.state,"request_id",str(uuid.uuid4()))
    return error_reponse(
        status_code=500,
        error="inter_server_error",
        message="Something went wrong .Please try again later",
        request_id=request_id
    )

fake_users={1:'alice',2:'bob'}
fake_docs={1:"doc_1",2:"doc_2"}

@app.get("/user/{user_id}")
def get_user(user_id:int):
    if user_id not in fake_users:
        raise NotFoundException("User",user_id)
    return {"user_id":user_id,"username":fake_users[user_id]}


@app.get("/document/{doc_id}")
def get_documents(token:str,doc_id:int):
    if not token.strip():
        raise UnAuthorizedException("Token required to access documents")
    if doc_id not in fake_docs:
        raise NotFoundException("Document",doc_id)
    return {"doc_id":doc_id,"document":fake_docs[doc_id]}

@app.post("/llm/generate")
async def generate(prompt:str,simulate_failure:bool=False):
    if simulate_failure:
        raise LLMServiceException("Open AI","Rate limit exceeded on provider side")
    return {"prompt":prompt,"response":"Response generated success"}

@app.get("/crash")
def crash():
    raise RuntimeError("Unexcepted error")

class LLMRequst(BaseModel):
    prompt:str=Field(...,max_length=100,min_length=1)
    temperature:float=Field(default=0.3,ge=0.1,le=0.9)

@app.get("/validate-test")
def validate_test(request:LLMRequst):
    return request.model_dump()

