import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import secrets
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
from typing import Optional
import httpx

app=FastAPI(title="Real google OAuth")

# ============================================================
# CONFIG — replace with your real credentials
# In production load from .env file
# ============================================================
GOOGLE_CLIENT_ID="1061194874306-tu5902lb4or43naf0jlij1kegob7k6mt.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="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"
GOOGLE_REDIRECT_URI= "http://localhost:8000/auth/google/callback"

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


oauth_states:dict={}
local_user_DB:dict={}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family: Arial; max-width: 400px; margin: 100px auto; text-align: center;">
        <h2>🤖 My Gen AI App</h2>
        <p>Sign in to access the AI features</p>
        <a href="/auth/google/login">
            <button style="padding: 10px 20px; font-size: 16px; cursor: pointer;">
                🔵 Sign in with Google
            </button>
        </a>
    </body>
    </html>
    """

@app.get("/auth/google/login")
def google_login():
    state=secrets.token_urlsafe(32)
    oauth_states[state]=True

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",   # what info we want
        "state": state,
        "access_type": "offline",          # get refresh token too
        "prompt": "select_account"         # always show account picker
    }
    query_string="&".join(f"{k}={v}" for k,v in params.items())
    google_url=f"{GOOGLE_AUTH_URL}?{query_string}"
    print(f"[OAUTH] Redirecting to google | state :{state[:8]}....")
    print(google_url)
    return RedirectResponse(url=google_url)


@app.get("/auth/google/callback")
async def google_callback(code:Optional[str]=None,state:Optional[str]=None,error:Optional[str]=None):
    if error:
        raise HTTPException(status_code=400,detail=f"Google Auth error {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400,detail="Missing code or state")
    
    if state not in oauth_states:
        raise HTTPException(status_code=400,detail="Invalid state prameter - possible CSRF attack")
    #print(f"code:{code}")
    #print(f"state: {state}")
    #print(f"error: {error}")
    del oauth_states[state]

    async with httpx.AsyncClient() as client:
        token_response= await client.post(
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
            raise HTTPException(status_code=400,detail=f"Failed to exchage code :{token_response.text}")
    
        token_data=token_response.json()
        #print(token_data)
        google_access_token=token_data["access_token"]
        print(f"[OAUTH] got google access token")
        
        userinfo_response=await client.get(
            url=GOOGLE_USERINFO_URL,
            headers={"Authorization":f"Bearer {google_access_token}"}
        )
        if userinfo_response.status_code!=200:
            raise HTTPException(status_code=400,detail="Failed to fetch user info from google")
        google_user=userinfo_response.json()
        print(google_user)

        email=google_user['email']
        if not google_user.get('verified_email'):
            raise HTTPException(status_code=400,detail="Google account email not verified")
        
        if email not in local_user_DB:
            local_user_DB[email]={
                "id":len(local_user_DB)+1,
                "email":email,
                "name":google_user.get("name"),
                "picture":google_user.get("picture"),
                "google_id":google_user.get('id'),
                "role":"user",
                "auth_provider":"google"
            }
            print(f"[OAUTH] New user registered :{email}")
        else:
            print(f"[OAUTH] Returning user :{email}")
        user=local_user_DB[email]
        return {
            "message":f"Welcome {user['name']}",
            "user":{
                "email":user['email'],
                "name":user['name'],
                "picture":user['picture']
            }
        }


        


