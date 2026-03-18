import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,HTTPException,Depends
from fastapi.responses import HTMLResponse,RedirectResponse
import secrets
import httpx
from fastapi.security import OAuth2PasswordBearer
from jose import jwt,JWTError
from datetime import datetime,timedelta,timezone
from typing import Optional
from pydantic import BaseModel

app=FastAPI(title="OAuth2 +JWT Complete")

GOOGLE_CLIENT_ID="1061194874306-tu5902lb4or43naf0jlij1kegob7k6mt.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="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"
GOOGLE_REDIRECT_URI= "http://localhost:8000/auth/google/callback"

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

YOUR_SECRET_KEY="your_super_secret_key"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/token",auto_error=False)

local_db_users:dict={}
oauth_states:dict={}

class UserResponse(BaseModel):
    id:int
    email:str
    name:str
    picture:Optional[str]
    role:str
    auth_provider:str

class TokenResponse(BaseModel):
    access_token:str
    token_type:str="bearer"
    expires_at:int
    user:UserResponse

def create_access_token(user:dict)->str:
    payload={
        "sub":user['email'],
        "id":user['id'],
        "role":user['role'],
        "name":user['name'],
        "exp":datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    return jwt.encode(payload,key=YOUR_SECRET_KEY,algorithm=ALGORITHM)

async def get_current_user(token:str=Depends(oauth2_scheme))->dict:
    if not token:
        raise HTTPException(status_code=401,detail="Not authenticated")
    try:
        payload=jwt.decode(token,key=YOUR_SECRET_KEY,algorithms=[ALGORITHM])
        email=payload.get("sub")
        if not email :
            raise HTTPException(status_code=401,detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401,detail="Invalid token")
    
    user=local_db_users.get(email)

    if not user:
        raise HTTPException(status_code=401,detail="User not found")
    return user

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family: Arial; max-width: 500px; margin: 100px auto; text-align: center;">
        <h2>🤖 Gen AI Platform</h2>
        <p>Sign in to access AI features</p>
        <a href="/auth/google/login">
            <button style="padding: 12px 24px; font-size: 16px; background: #4285f4;
                           color: white; border: none; border-radius: 4px; cursor: pointer;">
                🔵 Continue with Google
            </button>
        </a>
        <br><br>
        <small>After login, copy the JWT token and use it in /docs</small>
    </body>
    </html>
    """

@app.get("/auth/google/login")
def google_login():
    state=secrets.token_urlsafe(32)
    oauth_states[state]=True

    params="&".join([
        f"client_id={GOOGLE_CLIENT_ID}",
        f"redirect_uri={GOOGLE_REDIRECT_URI}",
        "response_type=code",
        "scope=openid email profile",   # what info we want
        f"state={state}",
        "access_type=offline",          # get refresh token too
        "prompt=select_account"         # always show account picker
    ])
    google_url=f"{GOOGLE_AUTH_URL}?{params}"
    return RedirectResponse(url=google_url)

@app.get("/auth/google/callback")
async def google_callback(code:Optional[str]=None,state:Optional[str]=None,error:Optional[str]=None):
    if error:
        raise HTTPException(status_code=400,detail=f"OAuth error : {error}")
    if not code or not state or state not in oauth_states:
        raise HTTPException(status_code=400,detail="Invalid Oauth2 callback")
    del oauth_states[state]

    async with httpx.AsyncClient() as client:
        token_response=await client.post(
            url=GOOGLE_TOKEN_URL,
            data={
                "code":code,
                "client_id":GOOGLE_CLIENT_ID,
                "client_secret":GOOGLE_CLIENT_SECRET,
                "redirect_uri":GOOGLE_REDIRECT_URI,
                "grant_type":"authorization_code"
            }
        )

        if token_response.status_code!=200:
            raise HTTPException(status_code=400,detail="Token exchange failes")
        
        google_token=token_response.json()["access_token"]

        user_info=await client.get(
            url=GOOGLE_USERINFO_URL,
            headers={"Authorization":f"Bearer {google_token}"}
        )

        if user_info.status_code!=200:
            raise HTTPException(status_code=400,detail="Failed to fetch user info")
        
        google_user=user_info.json()

    if not google_user['verified_email']:
        raise HTTPException(status_code=400,detail="Email not verified with Google account")
    
    email=google_user['email']

    if email not in local_db_users:
        local_db_users[email]={
            "id":len(local_db_users)+1,
            "email":email,
            "name":google_user.get('name'),
            "picture":google_user.get('picture'),
            "google_id":google_user.get('id'),
            "role":"user",
            "auth_provider":"goolge",
            "created_at":datetime.now().isoformat()
        }
        print(f"[OAUTH] New user : {email}")
    else:
        print(f"[OAUTH] Returning user : {email}")

    user=local_db_users[email]
    print(user)
    access_token=create_access_token(user)
    return {
        "access_token":access_token,
        "token_type":"bearer",
        "expires_at":ACCESS_TOKEN_EXPIRE_MINUTES*60,
        "user":user
    }

@app.get("/me",response_model=UserResponse)
async def get_me(current_user:dict=Depends(get_current_user)):
    return current_user


@app.get("/ai/generate")
async def generate(prompt:str,current_user:dict=Depends(get_current_user)):
    return {
        "prompt":prompt,
        "response":f"Response from the prompt by {current_user['name']}",
        "model":"gpt-4"
    }



