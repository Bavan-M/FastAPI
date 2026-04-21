import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.resilience import openai_cb, groq_cb
from ws.manager import chat_manager
from ws.handlers import chat_handler
from sse.notifications import sse_hub
from models.schemas import WSMessageType
import hashlib


# ============================================================
# AUTH
# ============================================================

pwd_context   = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)

fake_users = {
    "alice":   {"id": 1, "username": "alice",   "role": "admin",
                "hashed_password": hash_password("pass123")},
    "bob":     {"id": 2, "username": "bob",     "role": "user",
                "hashed_password": hash_password("pass123")},
    "charlie": {"id": 3, "username": "charlie", "role": "user",
                "hashed_password": hash_password("pass123")},
}


def create_token(user: dict) -> str:
    return jwt.encode(
        {
            "sub": user["username"],
            "role": user["role"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
        },
        settings.secret_key,
        algorithm=settings.algorithm
    )


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return fake_users.get(payload.get("sub"))
    except JWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


# ============================================================
# MIDDLEWARE
# ============================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())[:8]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n🚀 {settings.app_name} v{settings.version} starting...")
    print(f"  → Default LLM model: {settings.groq_default_model}")
    print(f"  → LLM timeout:       {settings.llm_timeout}s")
    print(f"  → Circuit breaker:   trips at {settings.cb_failure_threshold} failures")
    print("✅ Ready!\n")

    # Background task — broadcast stats every 30s via SSE
    async def stats_broadcaster():
        while True:
            await asyncio.sleep(30)
            await sse_hub.broadcast("stats", chat_manager.stats)

    task = asyncio.create_task(stats_broadcaster())
    yield
    task.cancel()
    print(f"\n🛑 {settings.app_name} shutting down...")


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# AUTH ROUTES
# ============================================================

@app.post("/auth/login", tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = fake_users.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "access_token": create_token(user),
        "token_type":   "bearer",
        "username":     user["username"],
        "role":         user["role"]
    }


@app.get("/auth/tokens", tags=["Auth"])
def get_test_tokens():
    """Get tokens for all test users — dev only"""
    return {
        username: create_token(user)
        for username, user in fake_users.items()
    }


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    # Authenticate before accepting
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return

    user = verify_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Connect and handle all messages
    conn = await chat_manager.connect(websocket, user)

    # Notify SSE subscribers about new connection
    await sse_hub.broadcast("user_connected", {
        "username":    user["username"],
        "online_count": chat_manager.stats["total_connections"]
    })

    try:
        await chat_handler.handle_connection(conn)
    finally:
        await sse_hub.broadcast("user_disconnected", {
            "username":    user["username"],
            "online_count": chat_manager.stats["total_connections"]
        })


# ============================================================
# SSE ROUTES
# ============================================================

@app.get("/sse/notifications", tags=["SSE"])
async def sse_notifications(request: Request):
    """
    SSE stream for real-time notifications.
    Used by admin dashboard, notification systems.
    No auth required for demo — add in production.
    """
    client_id = str(uuid.uuid4())[:8]

    async def event_stream():
        async for event in sse_hub.stream(client_id):
            if await request.is_disconnected():
                break
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/sse/broadcast", tags=["SSE"])
async def broadcast_sse(
    event: str,
    message: str,
    current_user: dict = Depends(get_current_user)
):
    """Broadcast a notification via SSE to all subscribers"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    await sse_hub.broadcast(event, {"message": message, "from": current_user["username"]})
    return {"broadcast": True, "subscribers": len(sse_hub._queues)}


# ============================================================
# REST ROUTES
# ============================================================

@app.get("/rooms", tags=["Chat"])
def list_rooms(current_user: dict = Depends(get_current_user)):
    return {"rooms": chat_manager.list_rooms()}


@app.get("/rooms/{room_id}/history", tags=["Chat"])
def get_room_history(
    room_id: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    room = chat_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"room_id": room_id, "history": room.get_history(limit)}


@app.get("/users/online", tags=["Chat"])
def online_users(current_user: dict = Depends(get_current_user)):
    return {"online_users": chat_manager.get_online_users()}


@app.get("/stats", tags=["Admin"])
def get_stats(current_user: dict = Depends(get_current_user)):
    return {
        **chat_manager.stats,
        "circuit_breakers": {
            "openai":    openai_cb.status,
            "groq": groq_cb.status
        }
    }


@app.post("/admin/rooms", tags=["Admin"])
def create_room(
    name: str,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    try:
        room = chat_manager.create_room(name, current_user["username"])
        return {"room": room.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ============================================================
# BROWSER CHAT UI
# ============================================================

@app.get("/", response_class=HTMLResponse, tags=["UI"])
def chat_ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gen AI Streaming Chat</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: -apple-system, Arial, sans-serif;
                   background: #1a1a2e; color: #eee; height: 100vh;
                   display: flex; flex-direction: column; }

            header { background: #16213e; padding: 12px 20px;
                     display: flex; align-items: center; gap: 15px;
                     border-bottom: 1px solid #0f3460; }
            header h1 { font-size: 18px; color: #e94560; }
            #status   { font-size: 13px; color: #aaa; margin-left: auto; }

            .layout { display: flex; flex: 1; overflow: hidden; }

            /* Sidebar */
            .sidebar { width: 220px; background: #16213e;
                       border-right: 1px solid #0f3460;
                       display: flex; flex-direction: column; }
            .sidebar h3 { padding: 12px 15px; font-size: 12px;
                          color: #888; text-transform: uppercase; }
            .room-item { padding: 8px 15px; cursor: pointer;
                         font-size: 14px; color: #aaa; }
            .room-item:hover, .room-item.active { background: #0f3460; color: #fff; }
            .online-user { padding: 5px 15px; font-size: 13px; color: #4CAF50; }

            /* Chat area */
            .chat-area { flex: 1; display: flex; flex-direction: column; }
            #messages  { flex: 1; overflow-y: auto; padding: 15px;
                         display: flex; flex-direction: column; gap: 8px; }

            .msg { max-width: 70%; padding: 8px 12px; border-radius: 8px;
                   font-size: 14px; line-height: 1.5; }
            .msg.user { background: #0f3460; align-self: flex-end; }
            .msg.ai   { background: #1b4332; align-self: flex-start; color: #81c784; }
            .msg.system { background: transparent; color: #888;
                          font-size: 12px; align-self: center; font-style: italic; }
            .msg-header { font-size: 11px; color: #888; margin-bottom: 3px; }
            .msg-content { white-space: pre-wrap; }
            .streaming { border-left: 2px solid #4CAF50; padding-left: 8px; }

            /* Input */
            .input-area { padding: 12px 15px; background: #16213e;
                          border-top: 1px solid #0f3460;
                          display: flex; gap: 10px; align-items: center; }
            #msgInput  { flex: 1; padding: 10px 14px; border-radius: 20px;
                         border: 1px solid #0f3460; background: #1a1a2e;
                         color: #eee; font-size: 14px; outline: none; }
            #msgInput:focus { border-color: #e94560; }
            button { padding: 10px 18px; border-radius: 20px; border: none;
                     cursor: pointer; font-size: 14px; transition: 0.2s; }
            .btn-primary { background: #e94560; color: white; }
            .btn-primary:hover { background: #c73652; }
            .btn-secondary { background: #0f3460; color: #eee; }
            .hint { font-size: 11px; color: #888; padding: 4px 0; }

            /* SSE panel */
            .sse-panel { width: 200px; background: #16213e;
                         border-left: 1px solid #0f3460; padding: 10px; }
            .sse-panel h3 { font-size: 12px; color: #888;
                            text-transform: uppercase; margin-bottom: 8px; }
            #sseLog { font-size: 11px; color: #aaa; height: 300px;
                      overflow-y: auto; font-family: monospace; }
            .sse-event { padding: 3px 0; border-bottom: 1px solid #0f3460; }

            /* Login overlay */
            #loginOverlay { position: fixed; inset: 0; background: #1a1a2e;
                            display: flex; align-items: center;
                            justify-content: center; z-index: 100; }
            .login-box { background: #16213e; padding: 30px;
                         border-radius: 12px; border: 1px solid #0f3460;
                         width: 320px; }
            .login-box h2 { color: #e94560; margin-bottom: 20px; }
            .login-box select, .login-box button {
                width: 100%; padding: 10px; margin: 8px 0;
                border-radius: 6px; border: 1px solid #0f3460;
                background: #1a1a2e; color: #eee; font-size: 14px; }
            .login-box button { background: #e94560; cursor: pointer; }
        </style>
    </head>
    <body>

    <!-- Login Overlay -->
    <div id="loginOverlay">
        <div class="login-box">
            <h2>🤖 Gen AI Chat</h2>
            <p style="color:#aaa; margin-bottom:15px; font-size:13px">
                Select a user to connect. All passwords are <b>pass123</b>
            </p>
            <select id="userSelect">
                <option value="alice">Alice (admin)</option>
                <option value="bob">Bob (user)</option>
                <option value="charlie">Charlie (user)</option>
            </select>
            <button onclick="connect()">Connect</button>
        </div>
    </div>

    <!-- Main App -->
    <header>
        <h1>🤖 Gen AI Streaming Chat</h1>
        <span id="currentRoom" style="color:#81c784">general</span>
        <span id="status">Connecting...</span>
    </header>

    <div class="layout">

        <!-- Sidebar -->
        <div class="sidebar">
            <h3>Rooms</h3>
            <div id="roomList"></div>
            <h3 style="margin-top:15px">Online</h3>
            <div id="onlineList"></div>
        </div>

        <!-- Chat -->
        <div class="chat-area">
            <div id="messages"></div>
            <div class="hint" style="padding: 4px 15px">
                💡 Start with <b>@ai</b> to ask the AI — response streams to everyone in the room
            </div>
            <div class="input-area">
                <input id="msgInput" placeholder="Type a message... (@ai to ask AI)" />
                <button class="btn-primary" onclick="sendMessage()">Send</button>
                <button class="btn-secondary" onclick="sendTyping()">...</button>
            </div>
        </div>

        <!-- SSE Panel -->
        <div class="sse-panel">
            <h3>📡 SSE Events</h3>
            <div id="sseLog"></div>
        </div>

    </div>

    <script>
        let ws         = null;
        let token      = null;
        let username   = null;
        let currentRoom = 'general';
        let streamingMsg = null;

        const messages   = document.getElementById('messages');
        const sseLog     = document.getElementById('sseLog');
        const statusEl   = document.getElementById('status');
        const roomEl     = document.getElementById('currentRoom');

        // ---- LOGIN ----
        async function connect() {
            const user = document.getElementById('userSelect').value;

            // Get token
            const fd = new FormData();
            fd.append('username', user);
            fd.append('password', 'pass123');
            const res  = await fetch('/auth/login', { method: 'POST', body: fd });
            const data = await res.json();

            if (!data.access_token) {
                alert('Login failed');
                return;
            }

            token    = data.access_token;
            username = data.username;

            document.getElementById('loginOverlay').style.display = 'none';
            statusEl.textContent = `Connected as ${username}`;
            statusEl.style.color = '#81c784';

            // Connect WebSocket
            ws = new WebSocket(`ws://localhost:8000/ws/chat?token=${token}`);
            ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
            ws.onclose   = ()  => {
                statusEl.textContent = 'Disconnected';
                statusEl.style.color = '#e94560';
            };

            // Connect SSE
            connectSSE();
        }

        // ---- SSE ----
        function connectSSE() {
            const es = new EventSource('/sse/notifications');
            es.addEventListener('connected',         (e) => logSSE('connected', e.data));
            es.addEventListener('user_connected',    (e) => logSSE('🟢 joined', e.data));
            es.addEventListener('user_disconnected', (e) => logSSE('🔴 left', e.data));
            es.addEventListener('stats',             (e) => logSSE('📊 stats', e.data));
            es.addEventListener('heartbeat',         (e) => logSSE('💓 heartbeat', ''));
        }

        function logSSE(event, data) {
            const div = document.createElement('div');
            div.className = 'sse-event';
            const parsed = data ? JSON.parse(data) : {};
            div.textContent = `${event}: ${parsed.username || parsed.online_count || ''}`;
            sseLog.prepend(div);
        }

        // ---- MESSAGE HANDLING ----
        function handleMessage(data) {
            switch(data.type) {
                case 'welcome':
                    addSystemMsg(`Welcome ${data.username}! Joined: general`);
                    updateRooms(data.rooms);
                    updateOnline(data.online_users);
                    if (data.history?.length) {
                        data.history.forEach(m => addChatMsg(m));
                    }
                    break;

                case 'chat_message':
                    addChatMsg(data);
                    break;

                case 'user_joined':
                    addSystemMsg(`${data.username} joined ${data.room_id}`);
                    break;

                case 'user_left':
                    addSystemMsg(`${data.username} left ${data.room_id}`);
                    break;

                case 'room_joined':
                    currentRoom = data.room_id;
                    roomEl.textContent = data.room_id;
                    addSystemMsg(`You joined #${data.room_id}`);
                    if (data.history?.length) {
                        messages.innerHTML = '';
                        data.history.forEach(m => addChatMsg(m));
                    }
                    updateRooms([data.room]);
                    break;

                case 'ai_start':
                    addSystemMsg(`🤖 AI is responding...`);
                    // Create streaming message element
                    streamingMsg = createStreamingMsg();
                    break;

                case 'ai_token':
                    if (streamingMsg) {
                        streamingMsg.textContent = data.full_so_far;
                    }
                    break;

                case 'ai_done':
                    if (streamingMsg) {
                        streamingMsg.classList.remove('streaming');
                        streamingMsg = null;
                    }
                    addSystemMsg(`✅ AI done (${data.token_count} tokens)`);
                    break;

                case 'ai_error':
                    addSystemMsg(`❌ AI error: ${data.error}`);
                    streamingMsg = null;
                    break;

                case 'typing_indicator':
                    showTyping(data.username);
                    break;

                case 'pong':
                    // heartbeat received
                    break;

                case 'error':
                    addSystemMsg(`⚠️ ${data.message}`);
                    break;
            }
        }

        // ---- UI HELPERS ----
        function addChatMsg(data) {
            const isMe  = data.username === username;
            const isAI  = data.role === 'assistant' || data.username === 'AI Assistant';
            const div   = document.createElement('div');
            div.className = `msg ${isAI ? 'ai' : isMe ? 'user' : 'user'}`;
            div.innerHTML = `
                <div class="msg-header">${data.username} · ${new Date(data.timestamp).toLocaleTimeString()}</div>
                <div class="msg-content">${escapeHtml(data.content)}</div>
            `;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }

        function createStreamingMsg() {
            const wrapper = document.createElement('div');
            wrapper.className = 'msg ai';
            wrapper.innerHTML = `<div class="msg-header">AI Assistant · streaming...</div>`;
            const content = document.createElement('div');
            content.className = 'msg-content streaming';
            wrapper.appendChild(content);
            messages.appendChild(wrapper);
            messages.scrollTop = messages.scrollHeight;
            return content;
        }

        function addSystemMsg(text) {
            const div = document.createElement('div');
            div.className = 'msg system';
            div.textContent = text;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }

        let typingTimeout;
        function showTyping(user) {
            clearTimeout(typingTimeout);
            const existing = document.getElementById('typing-indicator');
            if (existing) existing.remove();
            const div = document.createElement('div');
            div.id = 'typing-indicator';
            div.className = 'msg system';
            div.textContent = `${user} is typing...`;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
            typingTimeout = setTimeout(() => div.remove(), 3000);
        }

        function updateRooms(rooms) {
            const list = document.getElementById('roomList');
            list.innerHTML = '';
            rooms.forEach(r => {
                const div = document.createElement('div');
                div.className = `room-item ${r.id === currentRoom ? 'active' : ''}`;
                div.textContent = `# ${r.name} (${r.member_count})`;
                div.onclick = () => joinRoom(r.id);
                list.appendChild(div);
            });
        }

        function updateOnline(users) {
            const list = document.getElementById('onlineList');
            list.innerHTML = users.map(u =>
                `<div class="online-user">● ${u.username}</div>`
            ).join('');
        }

        function escapeHtml(text) {
            return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }

        // ---- ACTIONS ----
        function sendMessage() {
            const content = document.getElementById('msgInput').value.trim();
            if (!content || !ws) return;
            ws.send(JSON.stringify({ type: 'chat', content, room_id: currentRoom }));
            document.getElementById('msgInput').value = '';
        }

        function sendTyping() {
            if (ws) ws.send(JSON.stringify({ type: 'typing', room_id: currentRoom }));
        }

        function joinRoom(roomId) {
            if (ws) {
                ws.send(JSON.stringify({ type: 'join_room', room_id: roomId }));
                currentRoom = roomId;
                roomEl.textContent = roomId;
                messages.innerHTML = '';
                document.querySelectorAll('.room-item').forEach(el => {
                    el.classList.toggle('active', el.textContent.includes(roomId));
                });
            }
        }

        // Enter to send
        document.getElementById('msgInput')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
    </body>
    </html>
    """