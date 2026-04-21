import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass,field
from fastapi import WebSocket
from datetime import datetime,timezone
from collections import deque
from core.config import settings
from typing import Optional

@dataclass
class Connection:
    id:str
    websocket:WebSocket
    username:str
    role:str
    user_id:int
    connected_at:datetime=field(default_factory=lambda: datetime.now(timezone.utc))
    rooms:set[str]=field(default_factory=set)

    async def send(self,message:dict)->bool:
        try:
            await self.websocket.send_json(data=message)
            return True
        except Exception:
            return False
        
    def to_dict(self)->dict:
        return {
            "username":self.username,
            "role":self.role,
            "connected_at":self.connected_at.isoformat(),
            "rooms":list(self.rooms)
        }
    

@dataclass
class Room:
    id:str
    name:str
    created_by:str
    created_at:datetime=field(default_factory=lambda: datetime.now(timezone.utc))
    members:set[str]=field(default_factory=set)
    history:deque=field(default_factory=lambda:deque(maxlen=settings.max_message_history))

    def add_message(self,msg:dict):
        self.history.append(msg)


    def get_history(self,limit:int=20)->list:
        return list(self.history)[:limit]
    
    def to_dict(self)->dict:
        return {
            "id":self.id,
            "name":self.name,
            "created_by":self.created_by,
            "member_count":len(self.members),
            "members":list(self.members),
            "created_at":self.created_at.isoformat()
        }
    

class ChatManager:
    """
    Central manager for all WebSocket connections and rooms.
    Single source of truth for who is connected and where.
    """
    def __init__(self):
        self._connection:dict[str,Connection]={}
        self._user_conns:dict[str,set[str]]={}
        self._rooms:dict[str,Room]={}
        self._room_conns:dict[str,set[str]]={}
        self._total_messages:int=0

        for room_id,name in [("general","General"),("ai-lab","AI Lab"),("random","Random")]:
            self._rooms[room_id]=Room(id=room_id,name=name,created_by="system")
            self._room_conns[room_id]=set()

    
    async def connect(self,websocket:WebSocket,user:dict)->Connection:
        await websocket.accept()
        conn=Connection(
            id=f"{user["username"]}_{id(websocket)}",
            websocket=websocket,
            username=user["username"],
            role=user["role"],
            user_id=user["id"]
        )
        self._connection[conn.id]=conn
        self._user_conns.setdefault(conn.username,set()).add(conn.id)
        print(f"[CM] Connected: {conn.username} | Total: {len(self._connection)}")
        return conn
    
    def disconnect(self,conn:Connection):
        # Leave all rooms
        for room_id in list(conn.rooms):
            self._room_conns.get(room_id,set()).discard(conn.id)
            if room_id in self._rooms:
                self._rooms[room_id].members.discard(conn.id)
        
        self._connection.pop(conn.id,None)
        self._user_conns.get(conn.username,set()).discard(conn.id)
        if not self._user_conns.get(conn.username):
            self._user_conns.pop(conn.username,None)

        print(f"[CM] Disconnected: {conn.username} | Total: {len(self._connection)}")


    def join_room(self,conn:Connection,room_id:str)->Optional[Room]:
        room=self._rooms.get(room_id)
        if not room:
            return None
        
        room.members.add(conn.username)
        self._room_conns.setdefault(room_id,set()).add(conn.id)
        conn.rooms.add(room_id)
        return room
    
    def leave_room(self,conn:Connection,room_id:str):
        if room_id in self._rooms:
            self._rooms[room_id].members.discard(conn.username)
        self._room_conns.get(room_id,set()).discard(conn.id)
        conn.rooms.discard(room_id)

    def get_room(self,room_id:str)->Optional[Room]:
        return self._rooms.get(room_id)
    
    def create_room(self,name:str,created_by:str)->Room:
        room_id=name.lower().replace(" ","-")
        if room_id in self._room:
            raise ValueError(f"Room {room_id} already exists")
        room=Room(id=room_id,name=name,created_at=created_by)
        self._rooms[room_id]=room
        self._room_conns[room_id]=set()
        return room
    
    async def send_to_conn(self,conn_id:str,message:dict)->bool:
        conn=self._connection.get(conn_id)
        return conn.send(message=message) if conn else False
    
    async def send_to_user(self,username:str,message:dict)->int:
        sent=0
        for conn_id in list(self._user_conns.get(username,set())):
            if await self.send_to_conn(conn_id=conn_id,message=message):
                sent+=1
        return sent
    
    async def broadcast_to_room(self,room_id:str,message:dict,exclude_conn_id:str=None)->int:
        sent=0
        failed=[]
        for conn_id in list(self._room_conns.get(room_id,set())):
            if conn_id==exclude_conn_id:
                continue
            conn=self._connection.get(conn_id)
            if conn:
                if await conn.send(message=message):
                    sent+=1
                else:
                    failed.append(conn_id)
        
        for conn_id in failed:
            conn=self._connection.get(conn_id)
            if conn:
                self.disconnect(conn=conn)
        self._total_messages=sent
        return sent
    
    async def broadcast_to_all(self,message:dict,exclude:str=None)->int:
        sent=0
        for conn_id,conn in self._connection.items():
            if conn_id!=exclude:
                if await conn.send(message=message):
                    sent+=1
        return sent
    
    def list_rooms(self)->list:
        return [room.to_dict() for room in self._rooms.values()]
    

    def get_online_users(self)->list:
        return [
            {"username":username,"connections":len(connection)} for username,connection in self._user_conns.items()
        ]
    
    def is_online(self,username:str)->bool:
        return username in self._user_conns
    
    @property
    def stats(self)->dict:
        return {
            "total_connections":len(self._connection),
            "unique_users":len(self._user_conns),
            "active_rooms":len([room for room in self._rooms.values() if room.members]),
            "total_messages":self._total_messages,
            "rooms":self.list_rooms()
        }
    
chat_manager=ChatManager()

    

    
