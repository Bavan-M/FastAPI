import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,WebSocket,WebSocketDisconnect,Query
from dataclasses import dataclass,field
from collections import deque
from datetime import datetime,timezone

app=FastAPI(title="Websocket Rooms")

@dataclass
class Room:
    id:str
    name:str
    created_by:str
    is_private:bool=False
    max_members:int=100
    members:set[str]=field(default_factory=set)
    # Keep last 50 messages for history
    message_history:deque=field(default_factory=lambda: deque(maxlen=50))

    def add_member(self,username:str)->bool:
        if len(self.members)>self.max_members:
            return False
        self.members.add(username)
        return True
    
    def remove_member(self,username:str):
        self.members.discard(username)

    def add_message(self,message:str):
        self.message_history.append(message)

    def get_history(self,limit:int=20)->list:
        messages=list(self.message_history)
        return messages[-limit:]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "is_private": self.is_private,
            "member_count": len(self.members),
            "members": list(self.members)
        }
    
# ============================================================
# ROOM MANAGER
# ============================================================
class RoomManager:
    def __init__(self):
        self._rooms:dict[str,Room]={}
        self._conn_rooms:dict[str,set[str]]={}
        self._room_conns:dict[str,set[str]]={}
        self._connections:dict[str,tuple]={}
        self._create_default_rooms()

    def _create_default_rooms(self):
        for room_id,name in [("general","General"),("ai-chat","AI Chat"),("random","Random")]:
            self._rooms[room_id]=Room(id=room_id,name=name,created_by="system")
            self._room_conns[room_id]=set()

    async def connect(self,websoket:WebSocket,user:dict)->str:
        await websoket.accept()
        conn_id=f"{user["username"]}_{id(websoket)}"
        self._connections[conn_id]=(websoket,user)
        self._conn_rooms[conn_id]=set()
        return conn_id
    
    def disconnect(self,conn_id:str):
        # Leave all rooms
        for room_id in list(self._conn_rooms.get(conn_id,[])):
            self._room_conns.get(room_id.set()).discard(conn_id)
            room=self._rooms.get(room_id)
            if room:
                _,user=self._connections.get(conn_id,(None,{}))
                if user:
                    room.remove_member(user.get("username",""))
        self._conn_rooms.pop(conn_id,None)
        self._connections.pop(conn_id,None)

    def create_room(self,room_id:str,name:str,created_by:str,max_members:int=100,is_private:bool=False)->Room:
        if room_id in self._rooms:
            raise ValueError(f"Room '{room_id}' already exists")
        room=Room(id=room_id,name=name,created_by=created_by,is_private=is_private,max_members=max_members)
        self._rooms[room_id]=room
        self._room_conns[room_id]=set()
        return room
    
    async def broadcast_to_room(self,room_id:str,message:dict,exclude_conn_id:str=None)->int:
        conn_ids=self._room_conns.get(room_id,set())
        sent=0
        failed=[]
        for conn_id in list(conn_ids):
            if conn_id==exclude_conn_id:
                continue
            ws,_=self._connections.get(conn_id,(None,{}))
            if ws:
                try:
                    await ws.send_json(message)
                    sent+=1
                except Exception:
                    failed.append(conn_id)
        for conn_id in failed:
            self.disconnect(conn_id)
        return sent
    
    async def send_message_to_room(self,conn_id:str,room_id:str,content:str)->bool:
        room=self._rooms.get(room_id)
        if not room:
            return False
        if room_id not in self._conn_rooms.get(conn_id,set()):
            return False
        _,user=self._connections.get(conn_id,(None,{}))
        if not user:
            return False
        message = {
            "type": "room_message",
            "room_id": room_id,
            "from": user["username"],
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Save to history
        room.add_message(message=message)

        # Broadcast to room
        await self.broadcast_to_room(room_id=room_id,message=message)
        return True


    
    async def join_room(self,room_id:str,conn_id:str)->bool:
        room=self._rooms.get(room_id)
        if not room:
            return False
        ws,user=self._connections.get(conn_id,(None,{}))
        if not ws:
            return False
        username=user.get("username","")
        if not room.add_member(username=username):
            await ws.send_json({"type":"error","message":f"Room '{room_id}' is full"})
            return False
        
        self._conn_rooms[conn_id].add(room_id)
        self._room_conns[room_id].add(conn_id)

        # Send room history to new member
        history=await room.get_history()
        await ws.send_json({"type":"room_joined","room_id":room.id,"room_name":room.name,"members":list(room.members),"history":history})

        # Notify room members
        await self.broadcast_to_room(room_id=room_id,
                                     message={"type":"member_joined","room_id":room_id,"username":username,"member_count":len(room.members)},
                                     exclude_conn_id=conn_id)
        return True
    
    async def leave_room(self,conn_id:str,room_id:str):
        room=self._rooms.get(room_id)
        if not room:
            return 
        ws,user=self._connections(conn_id,(None,{}))
        username=user.get("username","") if user else ""

        room.remove_member(username=username)
        self._room_conns.get(room_id,set()).discard(conn_id)
        self._conn_rooms.get(conn_id,set()).discard(room_id)

        if ws:
            await ws.send_json({"type":"room_left","room_id":room_id})
        await self.broadcast_to_room(room_id=room_id,message={"type":"member_left","room_id":room_id,"username":username,"member_count":len(room.members)})


room_manager = RoomManager()

fake_users = {
    "alice":   {"id": 1, "username": "alice",   "role": "admin"},
    "bob":     {"id": 2, "username": "bob",     "role": "user"},
    "charlie": {"id": 3, "username": "charlie", "role": "user"},
}


@app.websocket("/ws")
async def websocket_rooms(
    websocket: WebSocket,
    username: str = Query("anonymous")
):
    user = fake_users.get(username, {
        "id": 0, "username": username, "role": "guest"
    })
    conn_id = await room_manager.connect(websocket, user)

    # Send available rooms
    await websocket.send_json({
        "type": "connected",
        "conn_id": conn_id,
        "available_rooms": room_manager.list_rooms()
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "join_room":
                room_id = data.get("room_id")
                success = await room_manager.join_room(conn_id, room_id)
                if not success:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Cannot join room '{room_id}'"
                    })

            elif msg_type == "leave_room":
                await room_manager.leave_room(conn_id, data.get("room_id"))

            elif msg_type == "room_message":
                await room_manager.send_message_to_room(
                    conn_id,
                    data.get("room_id"),
                    data.get("content", "")
                )

            elif msg_type == "create_room":
                if user["role"] != "admin":
                    await websocket.send_json({
                        "type": "error",
                        "message": "Only admins can create rooms"
                    })
                    continue
                try:
                    room = room_manager.create_room(
                        room_id=data["room_id"],
                        name=data["name"],
                        created_by=username,
                        is_private=data.get("is_private", False)
                    )
                    await websocket.send_json({
                        "type": "room_created",
                        "room": room.to_dict()
                    })
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg_type == "list_rooms":
                await websocket.send_json({
                    "type": "rooms_list",
                    "rooms": room_manager.list_rooms()
                })

            elif msg_type == "my_rooms":
                await websocket.send_json({
                    "type": "my_rooms",
                    "rooms": room_manager.get_user_rooms(conn_id)
                })

    except WebSocketDisconnect:
        room_manager.disconnect(conn_id)

        


