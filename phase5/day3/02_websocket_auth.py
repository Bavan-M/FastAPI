import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Depends,Request,HTTPException,WebSocket,Query,WebSocketDisconnect
from passlib.context import CryptContext
import hashlib
from jose import jwt,JWTError
from datetime import datetime,timedelta,timezone
from typing import Optional
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
import asyncio

app=FastAPI(title="Websocket Auth")

SECRET_KEY="your-secret-key-32-char-minimum"
ALGORITHM="HS256"
pwd_context=CryptContext(schemes=["argon2"],deprecated="auto")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)

fake_users={
    "alice":{
        "id":1,
        "username":"alice",
        "role":"admin",
        "hashed_password":hash_password("pass123")
    },
    "bob":{
        "id":2,
        "username":"bob",
        "role":"user",
        "hashed_password":hash_password("pass456")
    }
}

def create_token(username:str,role:str)->str:
    return jwt.encode(
        {
            "sub":username,
            "role":role,
            "exp":datetime.now(timezone.utc)+timedelta(minutes=15),
        },
        key=SECRET_KEY
    )

def verify_token(token:str)->Optional[dict]:
    try:
        payload=jwt.decode(token=token,key=SECRET_KEY,algorithms=[ALGORITHM])
        return fake_users.get(payload.get("sub"))
    except JWTError:
        return None
    


# ============================================================
# AUTH METHOD 1 — Token as query parameter
# ws://localhost/ws/chat?token=eyJ...
# Most common approach for WebSockets
# ============================================================
@app.websocket("/ws/auth/query-token")
async def ws_query_token(websocket:WebSocket,token:Optional[str]=Query(None)):
    # Authenticate BEFORE accepting
    if not token:
        await websocket.close(code=4001,reason="Token Required")
        return 
    user=verify_token(token)
    if not user:
        await websocket.close(code=4001,reason="Invalid Token")
        return 
    await websocket.accept()
    print(f"[WS] Authenticated: {user['username']} ({user['role']})")

    await websocket.send_json({
        "type":"auth_success",
        "user":user["username"],
        "role":user["role"]
    })
    try:
        while True:
            data=await websocket.receive_json()
            await websocket.send_json(
                {
                    "type":"message",
                    "from":user["username"],
                    "content":data.get("content","")
                }
            )
    except WebSocketDisconnect:
        print(f"[WS] {user['username']} disconnected")


# ============================================================
# AUTH METHOD 2 — Token in first message
# Connect → send auth message → authenticated
# ============================================================

@app.websocket("/ws/auth/first-message")
async def wa_first_message(websocket:WebSocket):
    await websocket.accept()

    # Wait for auth message as first message
    try:
        auth_data=await asyncio.wait_for(
            websocket.receive_json(),
            timeout=5.0  # must auth within 5 seconds
        )
    except asyncio.TimeoutError:
        await websocket.send_json({"type":"error","message":"Auth timeout"})
        await websocket.close(code=4002,reason="Auth timeout")
        return
    if auth_data.get("type")!="auth" or not auth_data.get("token"):
        await websocket.send_json({"type":"error","message":"Send auth message first"})
        await websocket.close(code=4001)
        return 
    user=verify_token(token=auth_data["token"])
    if not user:
        await websocket.send_json({"type":"error","message":"Invalid token"})
        await websocket.close(code=4001)
        return 
    await websocket.send_json({"type":"auth_success","user":user["username"]})
    print(f"[WS] Authenticated via first message: {user['username']}")

    try:
        while True:
            data=await websocket.receive_json()
            await websocket.send_json({
                "type":"message",
                "from":user["username"],
                "content":data.get("content")
            })
            print(data)
    except WebSocketDisconnect:
        print(f"[WS] {user['username']} disconnected")


# ============================================================
# AUTH METHOD 3 — Role-based WebSocket access
# ============================================================
@app.websocket("/ws/admin/stream")
async def ws_admin_only(websocket:WebSocket,token:Optional[str]=Query(None)):
    if not token:
        await websocket.close(code=4001,reason="Token Required")
        return 
    user=verify_token(token)
    if not user or user["role"]!="admin":
        await websocket.close(code=4003,reason="Admin only")
        return
    await websocket.accept()
    await websocket.send_json({"type":"system","message":f"Admin stream active for user {user["username"]}"})
    
    try:
        counter=0
        while True:
            counter+=1
            await websocket.send_json({
                "type":"admin_update",
                "metric":"active_users",
                "value":counter*10
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print(f"[WS] Admin {user['username']} disconnected")




@app.post("/auth/login")
def login(from_data:OAuth2PasswordRequestForm=Depends()):
    user=fake_users.get(from_data.username)
    if not user or not verify_password(from_data.password,user["hashed_password"]):
        raise HTTPException(status_code=401,detail="Invalid credentials")
    token=create_token(user["username"],user["role"])
    return {"access_token":token,"token_type":"bearer"}


@app.get("/", response_class=HTMLResponse)
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WS Auth Test</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            #log { border: 1px solid #ccc; padding: 10px; height: 250px;
                   overflow-y: auto; font-family: monospace; font-size: 13px; }
            button { padding: 8px 16px; margin: 4px; cursor: pointer; }
            input  { padding: 8px; width: 250px; }
            .sent { color: blue; } .received { color: green; }
            .system { color: orange; } .error { color: red; }
        </style>
    </head>
    <body>
        <h2>🔐 WebSocket Auth Test</h2>

        <div>
            <input id="username" placeholder="alice or bob" value="alice" />
            <input id="password" placeholder="password" value="pass123" type="password" />
            <button onclick="getToken()">Get Token</button>
        </div>

        <div style="margin: 10px 0;">
            <input id="token" placeholder="Token will appear here..." style="width:400px" />
        </div>

        <div>
            <button onclick="connectQueryToken()">Connect (query token)</button>
            <button onclick="connectFirstMessage()">Connect (first message)</button>
            <button onclick="connectAdmin()">Connect Admin Stream</button>
            <button onclick="disconnect()">Disconnect</button>
        </div>

        <div style="margin: 10px 0;">
            <input id="msg" placeholder="Message..." />
            <button onclick="sendMsg()">Send</button>
        </div>

        <div id="log"></div>

        <script>
            let ws = null;
            const log = document.getElementById('log');

            function addLog(msg, type = 'system') {
                const div = document.createElement('div');
                div.className = type;
                div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
                log.appendChild(div);
                log.scrollTop = log.scrollHeight;
            }

            async function getToken() {
                const fd = new FormData();
                fd.append('username', document.getElementById('username').value);
                fd.append('password', document.getElementById('password').value);
                const res = await fetch('/auth/login', { method: 'POST', body: fd });
                const data = await res.json();
                if (data.access_token) {
                    document.getElementById('token').value = data.access_token;
                    addLog('Token received!', 'system');
                } else {
                    addLog('Login failed', 'error');
                }
            }

            function getStoredToken() {
                return document.getElementById('token').value;
            }

            function connectQueryToken() {
                disconnect();
                const token = getStoredToken();
                ws = new WebSocket(`ws://localhost:8000/ws/auth/query-token?token=${token}`);
                ws.onopen    = () => addLog('Connected (query token)', 'system');
                ws.onmessage = (e) => addLog(`← ${e.data}`, 'received');
                ws.onclose   = (e) => addLog(`Disconnected: ${e.reason}`, 'system');
                ws.onerror   = () => addLog('Error', 'error');
            }

            function connectFirstMessage() {
                disconnect();
                ws = new WebSocket('ws://localhost:8000/ws/auth/first-message');
                ws.onopen = () => {
                    addLog('Connected — sending auth...', 'system');
                    ws.send(JSON.stringify({ type: 'auth', token: getStoredToken() }));
                };
                ws.onmessage = (e) => addLog(`← ${e.data}`, 'received');
                ws.onclose   = (e) => addLog(`Disconnected: ${e.reason}`, 'system');
            }

            function connectAdmin() {
                disconnect();
                const token = getStoredToken();
                ws = new WebSocket(`ws://localhost:8000/ws/admin/stream?token=${token}`);
                ws.onopen    = () => addLog('Connected admin stream', 'system');
                ws.onmessage = (e) => addLog(`← ${e.data}`, 'received');
                ws.onclose   = (e) => addLog(`Closed: ${e.reason}`, 'system');
            }

            function sendMsg() {
                const msg = document.getElementById('msg').value;
                if (ws?.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ content: msg }));
                    addLog(`→ ${msg}`, 'sent');
                    document.getElementById('msg').value = '';
                }
            }

            function disconnect() {
                if (ws) { ws.close(); ws = null; }
            }
        </script>
    </body>
    </html>
    """


