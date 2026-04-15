import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
from fastapi import FastAPI,WebSocket,WebSocketDisconnect
from datetime import datetime,timezone,timedelta
import time
from jose import jwt,JWTError
from typing import Optional
from fastapi.responses import HTMLResponse

app=FastAPI(title="Websocket chat")

SECRET_KEY="your-secret-key-32-chars-minimum"
ALGORITHM="HS256"

class ConnectionManager:
    """Manages all active websocket connections.
    In production store in Redis for multi servent support.
    """
    def __init__(self):
        self.connections:dict={}

    async def connect(self,websocket:WebSocket,user:dict)->str:
        await websocket.accept()
        conn_id=f"{user["username"]}_{id(websocket)}"
        self.connections[conn_id]={
            "ws":websocket,
            "user":user,
            "connected_at":datetime.now(timezone.utc).isoformat()
        }
        print(f"[WS] Connected: {conn_id} | Total: {len(self.connections)}")
        print(f"Stored connection: {self.connections[conn_id]['ws']}")  # Debug: should show WebSocket object
        return conn_id
    
    async def disconnect(self,conn_id:str):
        self.connections.pop(conn_id,None)
        print(f"[WS] Disconnected: {conn_id} | Total: {len(self.connections)}")

    async def send_to_connection(self,conn_id:str,message:str):
        conn=self.connections.get(conn_id)
        if conn:
            try:
                await conn["ws"].send_json(message)
            except Exception:
                await self.disconnect(conn_id)

    async def broadcast(self,message:dict,exclude:str=None):
        """Send messages to all Clients"""
        disconnected=[]
        print(f"message : {message}")
        print(f"exclude : {exclude}")
        print(f"Connections : {self.connections}")
        for conn_id,conn in self.connections.items():
            print(f"conn_id: {conn_id}")
            print(f"conn : {conn}")
            if conn_id==exclude:
                continue
            try:
                await conn["ws"].send_json(message)
            except Exception as e:
                disconnected.append(conn_id)
        for conn_id in disconnected:
            await self.disconnect(conn_id)

    def get_online_users(self)->list:
        return[
            {
                "username":conn["user"]["username"],
                "connected_at":conn["connected_at"]
            }
            for conn in self.connections.values()
        ]
    #just avoid paranthesis the method becomes the instance variable
    @property
    def total_connections(self)->int:
        return len(self.connections)
    
manager=ConnectionManager()

def make_message(msg_type:str,**kwargs)->dict:
    return {
        "type":msg_type,
        "timestamp":datetime.now(timezone.utc).isoformat(),
        **kwargs
    }

fake_users = {
    "alice": {"id": 1, "username": "alice", "role": "admin"},
    "bob":   {"id": 2, "username": "bob",   "role": "user"},
    "charlie": {"id": 3, "username": "charlie", "role": "user"},
}

def get_token_for_user(username:str)->str:
    return jwt.encode(
        {
            "sub":username,
            "exp":datetime.now(timezone.utc)+timedelta(hours=1)
        },
        key=SECRET_KEY,
        algorithm=ALGORITHM
    )

def verify_token(token:str)->Optional[dict]:
    try:
        payload=jwt.decode(token,key=SECRET_KEY,algorithms=[ALGORITHM])
        return fake_users.get(payload.get("sub"))
    except JWTError:
        return None
    

# ============================================================
# CHAT WEBSOCKET
# ============================================================
@app.websocket("/ws/chat")
async def websocket_chat(websocket:WebSocket,token:Optional[str]=None):
    if not token:
        await websocket.close(code=4001,reason="Token Required")
        return  
    user=verify_token(token)
    print(f"User: {user}")
    if not user:
        await websocket.close(code=4001,reason="Invalid token")
        return
    conn_id=await manager.connect(websocket,user)
    # Notify everyone that user joined
    await manager.broadcast(
        message=make_message(msg_type="user_joined",uername=user["username"],online_count=manager.total_connections),
        exclude=conn_id
    )

    # Send welcome message to new user
    await manager.send_to_connection(
        conn_id=conn_id,
        message=make_message(msg_type="Welcome",message=f"Welcome {user['username']}",online_users=manager.get_online_users())
    )

    try:
        while True:
            data=await websocket.receive_json()
            msg_type=data.get("type","chat")
            if msg_type=="chat":
                # Broadcast chat message to everyone
                await manager.broadcast(
                    message=make_message(msg_type="chat",from_user=user["username"],content=data.get("content",""),role=user["role"])
                )
            elif msg_type=="private":
                # Send private message to specific user
                target=data.get("to")
                target_conn=next((cid for cid,c in manager.connections.items() if c["user"]["username"]==target),None)
                if target_conn:
                    await manager.send_to_connection(
                        conn_id=target_conn,
                        message=make_message(msg_type="private_message",from_user=user["username"],content=data.get("content",""),is_private=True)
                    )
                    await manager.send_to_connection(
                        conn_id=conn_id,
                        message=make_message(msg_type="private_sent",to_user=target,content=data.get("content",""))
                    )
                else:
                    await manager.send_to_connection(
                        conn_id=conn_id,
                        message=make_message(msg_type="error",message=f"{target} is not online")
                    )
            elif msg_type=="typing":
                # Broadcast typing indicator (exclude sender)
                await manager.broadcast(
                    message=make_message(msg_type="typing",username=user["username"]),
                    exclude=conn_id
                )
            elif msg_type=="get_online_users":
                await manager.send_to_connection(
                    conn_id=conn_id,
                    message=make_message(msg_type="online_users",users=manager.get_online_users())
                )
    except WebSocketDisconnect:
        await manager.disconnect(conn_id)
        await manager.broadcast(
            message=make_message(msg_type="user_left",username=user["username"],online_count=manager.total_connections)
        )


# ============================================================
# AI CHAT WEBSOCKET — streams LLM responses
# ============================================================

async def simulate_llm_stream(prompt:str):
    """Simulate streaming LLM response token by token"""
    response = f"I understand you're asking about: {prompt}. Here is my detailed response that comes token by token just like a real LLM would stream it."
    for token in response.split():
        yield token
        await asyncio.sleep(0.1)

@app.websocket("/ws/ai-chat")
async def websocket_ai_chat(websocket:WebSocket,token:Optional[str]=None):
    if not token:
        await websocket.close(code=4001,reason="Token required")
        return
    user=verify_token(token)
    if not user:
        await websocket.close(code=4001,reason="Invalid Token")
        return
    await websocket.accept()
    print(f"[AI CHAT] {user['username']} connected")

    await websocket.send_json(
        data=make_message(msg_type="system",message="Connected to AI chat.Send your prompts")
    )
    try:
        while True:
            data=await websocket.receive_json()
            prompt=data.get("content","")
            if not prompt:
                continue

            # Send typing indicator
            await websocket.send_json(
                data=make_message(msg_type="ai_typing",is_typing=True)
            )

            # Stream AI response token by token
            full_response=""
            async for token_text in simulate_llm_stream(prompt):
                full_response += token_text
                await websocket.send_json(make_message(
                    "ai_token",
                    token=token_text,
                    full_so_far=full_response.strip()
                ))

            # Send completion signal
            await websocket.send_json(make_message(
                "ai_complete",
                full_response=full_response.strip(),
                tokens_used=len(full_response.split())
            ))
    except WebSocketDisconnect:
        print(f"[AI CHAT] {user['username']} disconnected")



# ============================================================
# HTTP ENDPOINTS
# ============================================================

@app.get("/tokens")
def get_test_tokens():
    """Get test tokens for all users"""
    return {
        username: get_token_for_user(username)
        for username in fake_users
    }

@app.get("/stats")
def get_stats():
    return {
        "total_connections": manager.total_connections,
        "online_users": manager.get_online_users()
    }

# ============================================================
# BROWSER TEST PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def chat_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Chat</title>
        <style>
            body { font-family: Arial; max-width: 900px; margin: 30px auto; padding: 20px; }
            .container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .chat-box { border: 1px solid #ccc; padding: 10px; height: 350px;
                        overflow-y: auto; font-family: monospace; font-size: 13px; }
            button { padding: 8px 14px; margin: 3px; cursor: pointer; }
            input  { padding: 8px; width: 200px; }
            select { padding: 8px; }
            .msg-user  { color: #2196F3; }
            .msg-ai    { color: #4CAF50; }
            .msg-system{ color: #FF9800; }
            .msg-error { color: #f44336; }
            .msg-private{ color: #9C27B0; }
            h3 { margin: 10px 0 5px 0; }
        </style>
    </head>
    <body>
        <h2>💬 WebSocket Chat Demo</h2>

        <div>
            <select id="userSelect">
                <option value="alice">Alice (admin)</option>
                <option value="bob">Bob (user)</option>
                <option value="charlie">Charlie (user)</option>
            </select>
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
            <span id="status" style="margin-left:10px; color:gray">Disconnected</span>
        </div>

        <div class="container" style="margin-top:15px">
            <div>
                <h3>💬 Group Chat</h3>
                <div id="chatLog" class="chat-box"></div>
                <div style="margin-top:8px">
                    <input id="chatMsg" placeholder="Message..." />
                    <button onclick="sendChat()">Send</button>
                    <button onclick="sendTyping()">Typing...</button>
                </div>
                <div style="margin-top:5px">
                    <input id="privateTarget" placeholder="To (username)" style="width:120px"/>
                    <input id="privateMsg" placeholder="Private message" style="width:150px"/>
                    <button onclick="sendPrivate()">Send Private</button>
                </div>
            </div>

            <div>
                <h3>🤖 AI Chat</h3>
                <div id="aiLog" class="chat-box"></div>
                <div style="margin-top:8px">
                    <input id="aiMsg" placeholder="Ask AI anything..." style="width:250px"/>
                    <button onclick="sendToAI()">Ask AI</button>
                </div>
            </div>
        </div>

        <script>
            let chatWs = null;
            let aiWs   = null;
            let tokens = {};
            let currentUser = '';

            const chatLog = document.getElementById('chatLog');
            const aiLog   = document.getElementById('aiLog');
            const status  = document.getElementById('status');

            function log(el, msg, type = 'system') {
                const div = document.createElement('div');
                div.className = `msg-${type}`;
                div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
                el.appendChild(div);
                el.scrollTop = el.scrollHeight;
            }

            async function connect() {
                disconnect();
                currentUser = document.getElementById('userSelect').value;

                // Get tokens
                const res = await fetch('/tokens');
                tokens = await res.json();
                const token = tokens[currentUser];

                // Connect chat WS
                chatWs = new WebSocket(`ws://localhost:8000/ws/chat?token=${token}`);
                chatWs.onopen    = () => { status.textContent = `Connected as ${currentUser}`; status.style.color = 'green'; };
                chatWs.onmessage = (e) => handleChatMessage(JSON.parse(e.data));
                chatWs.onclose   = () => { status.textContent = 'Disconnected'; status.style.color = 'gray'; };

                // Connect AI WS
                aiWs = new WebSocket(`ws://localhost:8000/ws/ai-chat?token=${token}`);
                aiWs.onmessage = (e) => handleAIMessage(JSON.parse(e.data));
            }

            function handleChatMessage(data) {
                switch(data.type) {
                    case 'welcome':
                        log(chatLog, `Welcome! Online: ${data.online_users.map(u=>u.username).join(', ')}`, 'system');
                        break;
                    case 'chat':
                        log(chatLog, `${data.from_user}: ${data.content}`, 'user');
                        break;
                    case 'private_message':
                        log(chatLog, `[PRIVATE] ${data.from_user}: ${data.content}`, 'private');
                        break;
                    case 'private_sent':
                        log(chatLog, `[PRIVATE → ${data.to_user}]: ${data.content}`, 'private');
                        break;
                    case 'user_joined':
                        log(chatLog, `${data.username} joined (${data.online_count} online)`, 'system');
                        break;
                    case 'user_left':
                        log(chatLog, `${data.username} left (${data.online_count} online)`, 'system');
                        break;
                    case 'typing':
                        log(chatLog, `${data.username} is typing...`, 'system');
                        break;
                    case 'error':
                        log(chatLog, `Error: ${data.message}`, 'error');
                        break;
                }
            }

            let aiBuffer = '';
            function handleAIMessage(data) {
                switch(data.type) {
                    case 'system':
                        log(aiLog, data.message, 'system');
                        break;
                    case 'ai_typing':
                        log(aiLog, 'AI is thinking...', 'system');
                        aiBuffer = '';
                        break;
                    case 'ai_token':
                        // Update last AI message with streaming token
                        const msgs = aiLog.querySelectorAll('.msg-ai');
                        if (msgs.length && msgs[msgs.length-1].dataset.streaming) {
                            msgs[msgs.length-1].textContent = `AI: ${data.full_so_far}`;
                        } else {
                            const div = document.createElement('div');
                            div.className = 'msg-ai';
                            div.dataset.streaming = 'true';
                            div.textContent = `AI: ${data.token}`;
                            aiLog.appendChild(div);
                        }
                        aiLog.scrollTop = aiLog.scrollHeight;
                        break;
                    case 'ai_complete':
                        // Mark streaming done
                        const streamMsgs = aiLog.querySelectorAll('[data-streaming]');
                        streamMsgs.forEach(m => delete m.dataset.streaming);
                        log(aiLog, `[${data.tokens_used} tokens]`, 'system');
                        break;
                }
            }

            function sendChat() {
                const msg = document.getElementById('chatMsg').value;
                if (chatWs?.readyState === WebSocket.OPEN && msg) {
                    chatWs.send(JSON.stringify({ type: 'chat', content: msg }));
                    document.getElementById('chatMsg').value = '';
                }
            }

            function sendTyping() {
                if (chatWs?.readyState === WebSocket.OPEN) {
                    chatWs.send(JSON.stringify({ type: 'typing' }));
                }
            }

            function sendPrivate() {
                const to  = document.getElementById('privateTarget').value;
                const msg = document.getElementById('privateMsg').value;
                if (chatWs?.readyState === WebSocket.OPEN && to && msg) {
                    chatWs.send(JSON.stringify({ type: 'private', to, content: msg }));
                    document.getElementById('privateMsg').value = '';
                }
            }

            function sendToAI() {
                const msg = document.getElementById('aiMsg').value;
                if (aiWs?.readyState === WebSocket.OPEN && msg) {
                    aiWs.send(JSON.stringify({ type: 'chat', content: msg }));
                    document.getElementById('aiMsg').value = '';
                }
            }

            function disconnect() {
                chatWs?.close(); chatWs = null;
                aiWs?.close();   aiWs   = null;
            }

            // Enter key support
            ['chatMsg','privateMsg','aiMsg'].forEach(id => {
                document.getElementById(id).addEventListener('keypress', (e) => {
                    if (e.key !== 'Enter') return;
                    if (id === 'chatMsg') sendChat();
                    else if (id === 'privateMsg') sendPrivate();
                    else if (id === 'aiMsg') sendToAI();
                });
            });
        </script>
    </body>
    </html>
    """

            

