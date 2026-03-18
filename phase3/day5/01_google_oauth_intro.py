import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import httpx
import secrets
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from typing import Optional
from datetime import datetime

app=FastAPI(title="OAuth2 intro")


oauth_states:dict={}

def generate_state()->str:
    state=secrets.token_urlsafe(32)
    oauth_states[state]=True
    return state

def verify_state(state:str)->bool:
    if state in oauth_states:
        del oauth_states[state]
        return True
    return False


FAKE_GGOGLE_USERS={
    "code_alice":
    {
        "access_token":"google_token_alice",
        "id":"google_id_001",
        "email":"alice@gmail.com",
        "name":"Alice Smith",
        "picture":"https://example.com/alice.jpg",
        "verified_email":True
    },
    "code_bob":
    {
        "access_token":"google_token_bob",
        "id":"google_id_002",
        "email":"bob@gmail.com",
        "name":"Bob James",
        "picture":"https://example.com/bob.jpg",
        "verified_email":True
    }
}

local_user_DB:dict={}

@app.get("/", response_class=HTMLResponse)
def home():
    # Simple frontend simulation
    return """
    <html>
    <body>
        <h2>My Gen AI App</h2>
        <a href="/auth/google/login">
            <button>Sign in with Google</button>
        </a>
    </body>
    </html>
    """

@app.get("/auth/google/login")
def google_login():
    state=generate_state()
    return RedirectResponse(url=f"/auth/google/simulate?state={state}&code=code_alice")

@app.get("/auth/google/simulate")
def simulate_google_redirect(code:str,state:str):
    if not verify_state(state):
        raise HTTPException(status_code=400,detail="Invalid state- posible CSRF attack")
    
    return RedirectResponse(url=f"/auth/google/callback?code={code}&state={state}_verified")


@app.get("/auth/google/callback")
async def google_callback(code:str,state:Optional[str]=None):
    google_user=FAKE_GGOGLE_USERS.get(code)
    if not google_user:
        raise HTTPException(status_code=400,detail="Invalid authorization code")
    
    email=google_user["email"]
    if email not in local_user_DB:
        local_user_DB[email]={
            "id":len(local_user_DB)+1,
            "email":email,
            "name":google_user["name"],
            "picture":google_user["picture"],
            "role":"user",
            "auth_provider":"google",
            "created_at":datetime.now()
        }
        print(f"[OAUTH] new user created :{email}")
    else:
        print(f"[OAUTH] exisitng user logged in {email}")
    
    user=local_user_DB[email]
    return {
        "message":f"Welcome {user["name"]}",
        "user":user,
        "next_step":"Issue your JWT token"
    }




