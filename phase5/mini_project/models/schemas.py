from enum import Enum
from pydantic import BaseModel,Field
from datetime import datetime,timezone
from typing import Optional,List


class MessageRole(str,Enum):
    USER="user"
    ASSISTANT="assistant"
    SYSTEM="system"

class WSMessageType(str,Enum):
    # Client → Server
    CHAT="chat"
    JOIN_ROOM="join_room"
    LEAVE_ROOM="leave_room"
    TYPING="typing"
    PING="ping"

    # Server → Client
    WELCOME="welcome"
    ROOM_JOINED="room_joined"
    ROOM_LEFT="room_left"
    CHAT_MSG="chat_message"
    AT_START="ai_start"
    AI_TOKEN="ai_token"
    AI_DONE="ai_done"
    AI_ERROR="ai_error"
    USER_JOINED="user_joined"
    USER_LEFT="user_left"
    TYPING_IND="typing_indication"
    PONG="pong"
    ERROR="error"
    SYSTEM_MSG="system_message"

class ChatMessage(BaseModel):
    id:str
    role:MessageRole
    content:str
    username:str
    room_id:str
    timestamp:datetime=Field(default_factory=datetime.now(timezone.utc))
    tokens:Optional[int]=None
    model:Optional[str]=None

class RoomInfo(BaseModel):
    id:str
    name:str
    member_count:int
    members:List[str]
    created_at:datetime

class UserInfo(BaseModel):
    id:str
    username:str
    role:str

class SystemStats(BaseModel):
    total_connections:int
    unique_users:int
    active_rooms:int
    total_messages:int
    circuit_breakers:int


    