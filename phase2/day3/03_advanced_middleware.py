import time
import uuid
from fastapi import FastAPI,Request,Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import asyncio

app=FastAPI()

class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_ROUTES=["/","/health","/docs","/redoc","/openapi.json"]
    async def dispatch(self, request, call_next):
        if request.url.path in self.PUBLIC_ROUTES:
            return await call_next(request)
        
        auth_header = request.headers.get("Authorization")
        print(auth_header)
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401,content="Missing or invalid authorization header")
        
        token=auth_header.split(" ")[1]

        valid_token={"token-alice":"Alice","token-bob":"Bob"}
        username=valid_token.get(token)
        if not username:
            return JSONResponse(status_code=401,content={"details":"Invalid Token"})
        request.state.user=username
        return await call_next(request)
    
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response=await call_next(request)
            return response
        except Exception as e:
            print(f"[ERROR] Unhadled exception {e}")
            return JSONResponse(status_code=500,content={"details":"Internal Server error","request_id":getattr(request.state,"request_id","unkown")})
        
class TokenTrackingMIddleware(BaseHTTPMiddleware):
    total_tokens_used=0
    async def dispatch(self, request, call_next):
        response=await call_next(request)
        tokens_used=response.headers.get('X-Tokens-Used')
        print(f"[TOKENS_USED]:{tokens_used}")
        if tokens_used:
            self.__class__.total_tokens_used+=int(tokens_used)
            print(f"[TOKENS] used {tokens_used} | Total :{self.__class__.total_tokens_used}")
        return response
        

app.add_middleware(ErrorHandlingMiddleware)   
app.add_middleware(AuthMiddleware)
app.add_middleware(TokenTrackingMIddleware)



@app.get("/")
def read_toot():
    return {"message":"Public root not auth needed"}

@app.get("/health")
def health():
    return {"statu":"Ok"}

@app.get("/protected")
def protected(request:Request):
    return {"message":f"Hello {request.state.user},protected"}

@app.get("/ai/generate")
async def geenrate(prompt:str,request:Request):
    await asyncio.sleep(0.5)
    fake_tokens=len(prompt.split())*10
    response=JSONResponse({
        "prompt":prompt,
        "response":"Generated text here......",
        "user":request.state.user
    })
    response.headers['X-Tokens-Used']=str(fake_tokens)
    return response


@app.get("/crash")
def crash_route():
    raise RuntimeError("Something went wrong")

