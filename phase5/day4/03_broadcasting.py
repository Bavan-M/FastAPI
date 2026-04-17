import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,WebSocket,Query,WebSocketDisconnect
from dataclasses import dataclass,field
import asyncio
from datetime import datetime,timezone
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

app=FastAPI(title="Broadcasting Patterns")

@dataclass
class Connection:
    id:str
    websocket:WebSocket
    username:str
    role:str
    rooms:set[str]=field(default_factory=set)

    async def send(self,msg:dict)->bool:
        try:
            await self.websocket.send_json(data=msg)
            return True
        except Exception as e:
            print(f"EXCEPTION {e}")
            return False
    
class BroadcastManager:
    def __init__(self):
        self._conns:dict[str,Connection]={}
        self._user_conns:dict[str,set[str]]={}
        self._room_conns:dict[str,set[str]]={}

    async def connect(self,ws:WebSocket,user:dict)->Connection:
        await ws.accept()
        conn=Connection(id=f"{user["username"]}_{id(ws)}",websocket=ws,username=user["username"],role=user["role"])
        self._conns[conn.id]=conn
        self._user_conns.setdefault(conn.username,set()).add(conn.id)
        return conn
    
    def disconnect(self,conn:Connection):
        self._conns.pop(conn.id,None)
        self._user_conns.get(conn.username,set()).discard(conn.id)
        for room_id in conn.rooms:
            self._room_conns.get(room_id,set()).discard(conn.id)
    
    def join_room(self,conn:Connection,room_id:str):
        conn.rooms.add(room_id)
        self._room_conns.get(room_id,set()).add(conn.id)

    def leave_room(self,conn:Connection,room_id:str):
        conn.rooms.discard(room_id)
        self._room_conns.get(room_id,set()).discard(conn.id)

    # ============================================================
    # BROADCASTING PATTERNS
    # ============================================================
    async def broadcast_all(self,message:dict,exclude:str=None)->int:
        """Pattern 1 — Send to EVERYONE"""
        sent=0
        for conn_id,conn in list(self._conns.items()):
            if conn_id!=exclude:
                if await conn.send(msg=message):
                    sent+=1
        return sent
    
    async def broadcast_to_room(self,room_id:str,message:dict,exclude:str=None)->int:
        """Pattern 2 — Send to everyone IN a specific room"""
        conn_ids=self._room_conns.get(room_id,set())
        sent=0
        for conn_id in list(conn_ids):
            if conn_id==exclude:
                continue
            conn=self._conns.get(conn_id)
            if conn and await conn.send(msg=message):
                sent+=1
        return sent
    
    async def broadcast_to_role(self,role:str,message:str)->int:
        """Pattern 3 — Send to everyone with a specific role"""
        sent=0
        for conn in list(self._conns.values()):
            if conn.role==role:
                if await conn.send(msg=message):
                    sent+=1
        return sent
    
    async def send_to_user(self,username:str,message:dict)->int:
        """Pattern 4 — Send to specific user (all their tabs)"""
        conn_ids=self._user_conns.get(username,set())
        sent=0
        for conn_id in list(conn_ids):
            conn=self._conns.get(conn_id)
            if conn and await conn.send(msg=message):
                sent+=1
        return sent
    
    async def broadcast_to_users(self,usernames:list[str],message:dict)->int:
        """Pattern 5 — Send to a list of specific users"""
        sent=0
        for username in usernames:
            sent+=self.send_to_user(username,message)
        return sent
    
    async def broadcast_except_user(self,username:str,message:dict)->int:
        """Pattern 6 — Send to everyone EXCEPT specific user"""
        sent=0
        for conn in self._conns.values():
            if conn.username!=username:
                if await conn.send(msg=message):
                    sent+=1
        return sent
    
    async def broadcast_multi_romms(self,room_ids:list[str],message:dict)->int:
        """Pattern 7 — Send to members of MULTIPLE rooms (no duplicates)"""
        target_conn_ids=set()
        for room_id in list(room_ids):
            target_conn_ids.update(self._room_conns.get(room_id,set()))
        sent=0
        for conn_id in target_conn_ids:
            conn=self._conns.get(conn_id)
            if conn and await conn.send(msg=message):
                sent+=1
        return sent
    
    async def stream_to_room(self,room_id:str,tokens:str,sender:str,delay:int):
        """Pattern 8 — Stream tokens to everyone in a room (Gen AI pattern)"""
        # Notify room that streaming started
        await self.broadcast_to_room(room_id=room_id,
                                     message={
                                         "type":"stream_start",
                                         "from":sender,
                                         "room_id":room_id
                                     })
        full_text=""
        for token in tokens:
            full_text+=token
            await self.broadcast_to_room(room_id=room_id,
                                         message={
                                             "type":"stream_token",
                                             "token":token,
                                             "full_so_far":full_text,
                                             "room_id":room_id
                                         })
            await asyncio.sleep(delay=delay)

        # Notify room that streaming completed
        await self.broadcast_to_room(room_id=room_id,
                                     message={
                                         "type":"stream_done",
                                         "full_text":full_text,
                                         "room_id":room_id
                                     })
    # --- Stats ---
    @property
    def stats(self) -> dict:
        return {
            "total_connections": len(self._conns),
            "unique_users":      len(self._user_conns),
            "active_rooms":      {
                rid: len(conns)
                for rid, conns in self._room_conns.items()
                if conns
            }
        }
    
# ============================================================
# GLOBAL INSTANCE
# ============================================================

bm = BroadcastManager()

fake_users = {
    "alice":   {"id": 1, "username": "alice",   "role": "admin"},
    "bob":     {"id": 2, "username": "bob",     "role": "user"},
    "charlie": {"id": 3, "username": "charlie", "role": "user"},
}

DEFAULT_ROOMS = ["general", "ai-lab", "announcements"]

# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/ws")
async def ws_endpoint(websocket:WebSocket,username:str=Query("anon")):
    user=fake_users.get(username,{"id":0,"username":username,"role":"guest"})
    conn=await bm.connect(ws=websocket,user=user)

    # Auto-join general room
    bm.join_room(conn=conn,room_id="general")
    await conn.send(
        msg={
            "type":"connected",
            "username":username,
            "conn_id":conn.id,
            "auto_joined":["general"],
            "available_rooms": DEFAULT_ROOMS
        }
    )

    # Tell general room someone joined
    await bm.broadcast_to_room(room_id="general",
                               message=
                               {
                                   "type":"user_joined",
                                   "username":username,
                                   "room":"general"
                               },exclude=conn.id)
    
    try:
        while True:
            data=await websocket.receive_json()
            msg_type=data.get("type")

            # --- Room messages ---
            if msg_type=="room_message":
                room_id=data.get("room_id","general")
                await bm.broadcast_to_room(room_id=room_id,
                                           message=
                                           {
                                               "type":"room_message",
                                               "room_id":room_id,
                                               "from":username,
                                               "content":data.get("content",""),
                                               "timestamp":datetime.now(timezone.utc).isoformat()
                                           })
            # --- Join/leave rooms ---
            elif msg_type=="join_room":
                room_id=data["room_id"]
                bm.join_room(conn=conn,room_id=room_id)
                await conn.send(msg={"type":"joined_room","room_id":room_id})
                await bm.broadcast_to_room(room_id=room_id,
                                           message=
                                           {
                                               "type":"member_joined",
                                               "room_id":room_id,
                                               "username":username
                                           },exclude=conn.id)
            
            elif msg_type=="leave_room":
                room_id=data["room_id"]
                bm.leave_room(conn=conn,room_id=room_id)
                await bm.broadcast_to_room(room_id=room_id,
                                           message=
                                           {
                                               "type":"member_left",
                                               "room_id":room_id,
                                               "username":username
                                           })
            
            # --- Direct message ---
            elif msg_type=="dm":
                target=data.get("to")
                sent=await bm.send_to_user(username=target,
                                           message=
                                           {
                                               "type":"dm",
                                               "from":username,
                                               "content":data.get("content",""),
                                               "timestamp":datetime.now(timezone.utc).isoformat()
                                           })
                await conn.send(msg={
                    "type":"dm_status",
                    "to":target,
                    "delivered":sent>0
                })
            
            # --- Admin broadcast ---
            elif msg_type=="admin_broadcast":
                if conn.role!="admin":
                    await conn.send(msg={"type":"error","message":"Admins Only"})
                    continue
                count=await bm.broadcast_all(message=
                                             {
                                                 "type":"announcement",
                                                 "from":"ADMIN",
                                                 "content":data.get("content"),
                                                 "timestamp":datetime.now(timezone.utc).isoformat()
                                             })
                await conn.send(msg={"type":"broadcast_sent","reached":count})

            # --- AI stream to room ---
            elif msg_type=="ai_prompt":
                room_id=data.get("room_id","ai-lab")
                bm.join_room(conn=conn,room_id=room_id)

                # Stream simulated AI response to entire room
                prompt=data.get("content","")
                response = f"AI response to '{prompt}': This is streamed to everyone in {room_id} simultaneously."
                tokens=response.split()

                # Run streaming as background task
                asyncio.create_task(bm.stream_to_room(room_id=room_id,tokens=tokens,sender=username))
            
            # --- Stats ---
            elif msg_type == "stats":
                await conn.send({"type": "stats", **bm.stats})

    except WebSocketDisconnect:
        bm.disconnect(conn=conn)
        await bm.broadcast_to_room(room_id="general",
                                   message={"type":"user_left","username":username})

# ============================================================
# HTTP — trigger broadcasts from REST endpoints
# ============================================================
class AnnouncementRequest(BaseModel):
    content:str
    target:str="all" # all, room:general, role:admin, user:alice

@app.post("/broadcast")
async def http_broadcast(req:AnnouncementRequest):
    """
    Trigger a WebSocket broadcast from an HTTP endpoint.
    Useful for: admin panel, cron jobs, external events.
    """
    message={
        "type":"announcement",
        "content":req.content,
        "timestamp":datetime.now(timezone.utc).isoformat()
    }

    if req.target=="all":
        sent=await bm.broadcast_all(message=message)
    elif req.target.startswith("room:"):
        room_id=req.target.split(":")[1]
        sent=await bm.broadcast_to_room(room_id=room_id,message=message)
    elif req.target.startswith("role:"):
        role=req.target.split(":")[1]
        sent=await bm.broadcast_to_roll(role=role,message=message)
    elif req.target.startswith("user:"):
        username=req.target.split(":")[1]
        sent=await bm.send_to_user(username=username,message=message)
    else:
        return {"error":"Invalid target format"}
    return {"sent":sent,"target":req.target}

@app.get("/stats")
def get_stats():
    return bm.stats

# ============================================================
# BROWSER TEST PAGE
# ============================================================
@app.get("/", response_class=HTMLResponse)
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Broadcasting Test</title>
        <style>
            body { font-family: Arial; max-width: 1000px; margin: 30px auto; padding: 20px; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            .log  { border: 1px solid #ccc; padding: 8px; height: 250px;
                    overflow-y: auto; font-family: monospace; font-size: 12px; }
            button { padding: 7px 13px; margin: 3px; cursor: pointer; font-size: 13px; }
            input, select { padding: 7px; margin: 3px; font-size: 13px; }
            .t-msg    { color: #2196F3; }
            .t-system { color: #FF9800; }
            .t-ai     { color: #4CAF50; }
            .t-admin  { color: #9C27B0; font-weight: bold; }
            .t-error  { color: #f44336; }
            .t-dm     { color: #00BCD4; }
        </style>
    </head>
    <body>
        <h2>📡 Broadcasting Patterns</h2>

        <div>
            <select id="user">
                <option value="alice">Alice (admin)</option>
                <option value="bob">Bob</option>
                <option value="charlie">Charlie</option>
            </select>
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
            <b id="status" style="color:gray"> ● Disconnected</b>
        </div>

        <div class="grid" style="margin-top:15px">

            <div>
                <b>💬 Room Chat</b>
                <div id="roomLog" class="log"></div>
                <select id="roomSelect">
                    <option value="general">general</option>
                    <option value="ai-lab">ai-lab</option>
                    <option value="announcements">announcements</option>
                </select>
                <button onclick="joinRoom()">Join</button>
                <button onclick="leaveRoom()">Leave</button>
                <br>
                <input id="roomMsg" placeholder="Room message..." style="width:200px"/>
                <button onclick="sendRoomMsg()">Send</button>
            </div>

            <div>
                <b>🤖 AI Stream to Room</b>
                <div id="aiLog" class="log"></div>
                <input id="aiPrompt" placeholder="Ask AI..." style="width:200px"/>
                <button onclick="askAI()">Ask (streams to room)</button>
            </div>

            <div>
                <b>📩 Direct Messages</b>
                <div id="dmLog" class="log"></div>
                <input id="dmTo"  placeholder="To (username)" style="width:100px"/>
                <input id="dmMsg" placeholder="Message..." style="width:150px"/>
                <button onclick="sendDM()">Send DM</button>
            </div>

            <div>
                <b>📣 Admin Broadcast</b>
                <div id="adminLog" class="log"></div>
                <input id="adminMsg" placeholder="Announcement..." style="width:200px"/>
                <button onclick="adminBroadcast()">Broadcast All</button>
                <br><br>
                <button onclick="getStats()">Get Stats</button>
                <button onclick="triggerHttpBroadcast()">HTTP Broadcast</button>
            </div>
        </div>

        <script>
            let ws = null;

            const logs = {
                room:  document.getElementById('roomLog'),
                ai:    document.getElementById('aiLog'),
                dm:    document.getElementById('dmLog'),
                admin: document.getElementById('adminLog')
            };

            function log(target, msg, type = 'system') {
                const div = document.createElement('div');
                div.className = `t-${type}`;
                div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
                logs[target].appendChild(div);
                logs[target].scrollTop = logs[target].scrollHeight;
            }

            function connect() {
                disconnect();
                const user = document.getElementById('user').value;
                ws = new WebSocket(`ws://localhost:8000/ws?username=${user}`);

                ws.onopen = () => {
                    document.getElementById('status').textContent = ` ● Connected as ${user}`;
                    document.getElementById('status').style.color = 'green';
                };

                ws.onmessage = (e) => {
                    const data = JSON.parse(e.data);
                    handleMessage(data);
                };

                ws.onclose = () => {
                    document.getElementById('status').textContent = ' ● Disconnected';
                    document.getElementById('status').style.color = 'gray';
                };
            }

            // Track AI streaming state
            let aiStreaming = false;

            function handleMessage(data) {
                switch(data.type) {
                    case 'connected':
                        log('room', `Connected! Auto-joined: ${data.auto_joined}`, 'system');
                        break;
                    case 'room_message':
                        log('room', `[${data.room_id}] ${data.from}: ${data.content}`, 'msg');
                        break;
                    case 'joined_room':
                        log('room', `Joined room: ${data.room_id}`, 'system');
                        break;
                    case 'member_joined':
                        log('room', `${data.username} joined ${data.room_id}`, 'system');
                        break;
                    case 'member_left':
                        log('room', `${data.username} left ${data.room_id}`, 'system');
                        break;
                    case 'user_joined':
                        log('room', `${data.username} connected`, 'system');
                        break;
                    case 'user_left':
                        log('room', `${data.username} disconnected`, 'system');
                        break;
                    case 'dm':
                        log('dm', `From ${data.from}: ${data.content}`, 'dm');
                        break;
                    case 'dm_status':
                        log('dm', `DM to ${data.to}: ${data.delivered ? '✅' : '❌ offline'}`, 'system');
                        break;
                    case 'announcement':
                        log('admin', `📣 ${data.from || 'SERVER'}: ${data.content}`, 'admin');
                        break;
                    case 'broadcast_sent':
                        log('admin', `Broadcast reached ${data.reached} users`, 'system');
                        break;
                    case 'stream_start':
                        log('ai', `🤖 ${data.from} asked AI (streaming to room)...`, 'system');
                        aiStreaming = true;
                        break;
                    case 'stream_token':
                        // Update last AI message
                        const msgs = logs.ai.querySelectorAll('.streaming');
                        if (msgs.length) {
                            msgs[msgs.length-1].textContent = `AI: ${data.full_so_far}`;
                        } else {
                            const div = document.createElement('div');
                            div.className = 'streaming t-ai';
                            div.textContent = `AI: ${data.token}`;
                            logs.ai.appendChild(div);
                        }
                        logs.ai.scrollTop = logs.ai.scrollHeight;
                        break;
                    case 'stream_done':
                        document.querySelectorAll('.streaming').forEach(el => el.classList.remove('streaming'));
                        log('ai', `✅ Stream complete`, 'system');
                        break;
                    case 'stats':
                        log('admin', `Stats: ${JSON.stringify(data)}`, 'system');
                        break;
                    case 'error':
                        log('room', `Error: ${data.message}`, 'error');
                        break;
                }
            }

            function send(data) {
                if (ws?.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify(data));
                }
            }

            function joinRoom() {
                send({ type: 'join_room', room_id: document.getElementById('roomSelect').value });
            }

            function leaveRoom() {
                send({ type: 'leave_room', room_id: document.getElementById('roomSelect').value });
            }

            function sendRoomMsg() {
                const msg = document.getElementById('roomMsg').value;
                if (!msg) return;
                send({ type: 'room_message', room_id: document.getElementById('roomSelect').value, content: msg });
                document.getElementById('roomMsg').value = '';
            }

            function askAI() {
                const prompt = document.getElementById('aiPrompt').value;
                if (!prompt) return;
                const room = document.getElementById('roomSelect').value;
                send({ type: 'ai_prompt', content: prompt, room_id: room });
                document.getElementById('aiPrompt').value = '';
            }

            function sendDM() {
                const to  = document.getElementById('dmTo').value;
                const msg = document.getElementById('dmMsg').value;
                if (!to || !msg) return;
                send({ type: 'dm', to, content: msg });
                document.getElementById('dmMsg').value = '';
            }

            function adminBroadcast() {
                const msg = document.getElementById('adminMsg').value;
                if (!msg) return;
                send({ type: 'admin_broadcast', content: msg });
                document.getElementById('adminMsg').value = '';
            }

            function getStats() {
                send({ type: 'stats' });
            }

            async function triggerHttpBroadcast() {
                const res = await fetch('/broadcast', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content: 'HTTP-triggered announcement!',
                        target: 'all'
                    })
                });
                const data = await res.json();
                log('admin', `HTTP broadcast sent to ${data.sent} users`, 'system');
            }

            function disconnect() {
                ws?.close(); ws = null;
            }

            // Enter key support
            ['roomMsg','dmMsg','adminMsg','aiPrompt'].forEach(id => {
                document.getElementById(id)?.addEventListener('keypress', e => {
                    if (e.key !== 'Enter') return;
                    if (id === 'roomMsg') sendRoomMsg();
                    else if (id === 'dmMsg') sendDM();
                    else if (id === 'adminMsg') adminBroadcast();
                    else if (id === 'aiPrompt') askAI();
                });
            });
        </script>
    </body>
    </html>
    """
     




