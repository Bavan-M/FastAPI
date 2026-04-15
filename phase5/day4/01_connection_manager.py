import sys,os
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
from fastapi import FastAPI,WebSocket,WebSocketDisconnect,Query
from dataclasses import dataclass,field
from datetime import datetime,timezone
from typing import Set,Optional

app=FastAPI(title="Connection Manager")

@dataclass
class Connection:
    id:str
    websocket:WebSocket
    user_id:str
    username:str
    role:str
    connected_at:datetime=field(default_factory=datetime.now(timezone.utc))
    rooms:Set[str]=field(default_factory=set)
    metadata:dict=field(default_factory=dict)

    async def send(self,message:dict):
        """Send messsage to this connection like a prticluar room maybe"""
        try:
            await self.websocket.send_json(data=message)
            return True
        except Exception as e:
            print(f"[WS] Failed to send to {self.username}: {e}")
            return False
    
    def to_dict(self)->dict:
        return{
            "id":self.id,
            "username":self.username,
            "role":self.role,
            "connected_at":self.connected_at.isoformat(),
            "rooms":list(self.rooms)
        }

# ============================================================
# PRODUCTION CONNECTION MANAGER
# ============================================================
class ConnectionManager:
    def __init__(self):
        # All active connections
        self._connections:dict[str,Connection]={}

        # User → set of connection IDs (one user can have multiple tabs)
        self._user_connections:dict[str,set[str]]={}

        # Stats
        self._total_messages=0
        self.total_connected=0

    # --- Connection lifecycle ---
    async def connect(self,websocket:WebSocket,user:dict)->Connection:
        await websocket.accept()

        conn_id=f"{user["username"]}_{id(websocket)}"
        conn=Connection(id=conn_id,websocket=websocket,user_id=str(user["id"]),username=user["username"],role=user["role"])
        self._connections[conn_id]=conn

        # Track user → connections mapping
        # If Alice isn't in the system yet, create an empty set for her
        if user["username"] not in self._user_connections:
            self._user_connections[user["username"]]=set()
        self._user_connections[user["username"]].add(conn_id)
            # _user_connections = {
            #     "alice": {"alice_123", "alice_456"},  # 2 tabs!
            #     "bob": {"bob_789"}
            # }
        self.total_connected+=1
        print(f"[CM] Connected: {conn_id} | Total: {len(self._connections)}")
        return conn
    
    def disconnect(self,conn:Connection):
        # Remove from connections
        self._connections.pop(conn.id,None)

        # Remove from user mapping
        if conn.username in self._user_connections:
            self._user_connections[conn.username].discard(conn.id)
            if not self._user_connections[conn.username]:
                del self._user_connections[conn.username]
        print(f"[CM] Disconnected: {conn.id} | Total: {len(self._connections)}")

    # --- Sending messages ---
    async def send_to_connection(self,conn_id:str,message:dict)->bool:
        conn=self._connections.get(conn_id)
        if conn:
            success=await conn.send(message)
            if success:
                self._total_messages+=1
            return success
        return False
    
    async def send_to_user(self,username:str,message:dict)->int:
        """Send to ALL connections of a specific user (multi-tab support)"""
        conn_ids=self._user_connections.get(username,set())
        sent=0
        for conn_id in list(conn_ids):
            if await self.send_to_connection(conn_id=conn_id,message=message):
                sent+=1
        return sent
    
    async def broadcast(self,message:dict,exclude_conn_id:str=None,exclude_username:str=None,role_filter:str=None)->int:
        """Broadcast to all connections with optional filters"""
        sent=0
        failed=[]

        for conn_id,conn in self._connections.items():
            if exclude_conn_id and conn_id==exclude_conn_id:
                continue
            if exclude_username and conn.username==exclude_username:
                continue
            if role_filter and conn.role!=role_filter:
                continue
            success=await conn.send(message)
            if success:
                sent+=1
                self._total_messages+=1
            else:
                failed.append(conn_id)
        
        # Clean up failed connections
        for conn_id in failed:
            conn=self._connections.get(conn_id)
            if conn:
                self.disconnect(conn)
        return sent
    
    async def broadcast_to_users(self,usernames:list,message:dict)->int:
        """Broadcast to specific list of users"""
        sent=0
        for username in usernames:
            sent+=await self.send_to_user(username,message)
        return sent
    
    # --- Queries ---
    def get_connections(self,conn_id:str)->Optional[Connection]:
        return self._connections.get(conn_id)
    
    def get_user_connections(self,username:str)->list:
        conn_ids=self._user_connections.get(username,set())
        return [self._coonections[conn_id] for conn_id in conn_ids if conn_id in self._connections]
    
    def is_user_online(self,username:str)->bool:
        return username in self._user_connections
    
    def get_online_users(self)->list:
        return [
            {
                "username":username,
                "connections":len(conn_ids),
                "is_multi_tab":len(conn_ids)>1
            }
            for username,conn_ids in self._user_connections.items()
        ]
    
    @property
    def total_connections(self)->int:
        return len(self._connections)
    
    @property
    def stats(self) -> dict:
        return {
            "total_connections": len(self._connections),
            "unique_users": len(self._user_connections),
            "total_connected_ever": self._total_connected,
            "total_messages_sent": self._total_messages,
            "online_users": self.get_online_users()
        }

# ============================================================
# GLOBAL MANAGER INSTANCE
# ============================================================
manager=ConnectionManager()

fake_users = {
    "alice":   {"id": 1, "username": "alice",   "role": "admin"},
    "bob":     {"id": 2, "username": "bob",     "role": "user"},
    "charlie": {"id": 3, "username": "charlie", "role": "user"},
}


@app.websocket("/ws")
async def websocket_endpoint(websocket:WebSocket,username:str=Query("anonymous")):
    user=fake_users.get(username,{"id": 0, "username": username, "role": "guest"})
    conn=manager.connect(websocket=websocket,user=user)

    await manager.broadcast(
        message={"type":"useer_joined","username":username,"online":manager.total_connections},
        exclude_conn_id=conn.id
    )

    # Welcome new user
    await conn.send({
        "type":"welcome",
        "message":f"Welcome {username}",
        "online_users":manager.get_online_users(),
        "your_conn_id":conn.id
    })

    try:
        while True:
            data=await websocket.receive_json()
            msg_type=data.get("type")

            if msg_type=="broadcast":
                # Send to everyone
                count=await manager.broadcast(
                    message={"type":"message","from":username,"content":data["content"]},
                    exclude_conn_id=conn.id
                )
                await conn.send({"type":"sent","to":f"{count} users"})
            
            elif msg_type=="dm":
                # Direct message to specific user
                target=data.get("to")
                sent=manager.send_to_user(
                    username=target,
                    message={"type":"dm","from":username,"content":data["content"]}
                )
                await conn.send({"type":"dm_status","to":target,"delivered":sent>0,"tabs_reached":sent})
            
            elif msg_type=="ping":
                await conn.send({"type":"pong","timestamp":datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(conn=conn)
        await manager.broadcast(
            message={"type":"user_left","username":username,"online":manager.total_connections}
        )
@app.get("/stats")
def get_stats():
    return manager.stats