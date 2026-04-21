import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from models.schemas import WSMessageType
from datetime import datetime,timezone
from ws.manager import ChatManager,Connection,chat_manager
import uuid
from llm.client import llm_client
from models.schemas import MessageRole
import asyncio
from fastapi import WebSocketDisconnect

def make_msg(msg_type:WSMessageType,**kwargs):
    return {
        "type":msg_type,
        "timestamp":datetime.now(timezone.utc).isoformat(),
        **kwargs
    }

class ChatHandler:
    """Handles all incoming WebSocket messages.
    Each message type has its own handler method.
    """
    def __init__(self,manager:ChatManager):
        self.manager=manager


    async def _handle_chat(self,conn:Connection,data:dict):
        """
        Handle a chat message.
        If prompt starts with @ai — trigger LLM streaming response.
        Otherwise — broadcast to room as regular chat.
        """
        content=data.get("content","")
        room_id=data.get("toom_id","general")
        msg_id=str(uuid.uuid4())[:8]

        if not content:
            return 
        
        room=self.manager.get_room(room_id=room_id)
        if not room:
            await conn.send(message=make_msg(
                msg_type=WSMessageType.ERROR,
                message=f"Room '{room_id}' not found"
            ))
            return
        
        msg=make_msg(
            msg_type=WSMessageType.CHAT_MSG,
            id=msg_id,
            content=content,
            username=conn.username,
            room_id=room_id,
            role=MessageRole.USER
        )

        room.add_message(msg=msg)

        await self.manager.broadcast_to_room(room_id=room_id,message=msg)

        if content.lower().startswith("@ai"):
            prompt=content[3:].strip() or content
            asyncio.create_task(self._stream_ai_response(prompt=prompt,conn=conn,room_id=room_id))
        

    async def _stream_ai_response(self,prompt:str,conn:Connection,room_id:str):
        """Stream AI response token by token to the entire room.
        This is the core Gen AI streaming pattern.
        """
        room=self.manager.get_room(room_id=room_id)
        if not room:
            return 
        stream_id=str(uuid.uuid4())[:8]
        full_response=""
        token_count=0

        # Notify room AI is responding
        await self.manager.broadcast_to_room(
            room_id=room_id,
            message=make_msg(
                msg_type=WSMessageType.AT_START,
                stream_id=stream_id,
                room_id=room_id,
                triggered_by=conn.username
            )
        )

        try:
            # Stream tokens to entire room
            async for token in llm_client.stream(prompt=prompt):
                full_response+=token
                token_count+=1
                await self.manager.broadcast_to_room(
                    room_id=room_id,
                    message=make_msg(
                        msg_type=WSMessageType.AI_TOKEN,
                        stream_id=stream_id,
                        token=token,
                        full_so_far=full_response,
                        room_id=room_id

                    )
                )

            # Store complete AI message in history
            ai_msg=make_msg(
                msg_type=WSMessageType.CHAT_MSG,
                id=stream_id,
                content=full_response.strip(),
                username="AI Assistant",
                room_id=room_id,
                role=MessageRole.ASSISTANT,
                tokens=token_count,
                model="llama"
            )

            room.add_message(msg=ai_msg)

            # Notify room streaming is done
            await self.manager.broadcast_to_room(
                room_id=room_id,
                message=make_msg(
                    msg_type=WSMessageType.AI_DONE,
                    stream_id=stream_id,
                    room_id=room_id,
                    full_response=full_response.strip(),
                    token_count=token_count
                )
            )
        except Exception as e:
            print(f"[LLM] Streaming error: {e}")
            await self.manager.broadcast_to_room(
                room_id=room_id,
                message=make_msg(
                    msg_type=WSMessageType.AI_ERROR,
                    stream_id=stream_id,
                    room_id=room_id,
                    error=str(e)
                )
            )

    async def _handle_join_room(self,conn:Connection,data:dict):
        room_id=data.get("room_id")
        room=self.manager.join_room(conn=conn,room_id=room_id)
        if not room:
            await conn.send(message=make_msg(
                msg_type=WSMessageType.ERROR,
                message=f"Room '{room_id}' not found"
            ))
            return 
        
        await conn.send(message=make_msg(
            msg_type=WSMessageType.ROOM_JOINED,
            room_id=room_id,
            room=room.to_dict(),
            history=room.get_history()
        ))

        await self.manager.broadcast_to_room(
            room_id=room_id,
            message=make_msg(
                msg_type=WSMessageType.USER_JOINED,
                username=conn.username,
                room_id=room_id,
                member_count=len(room.members)
            ),
            exclude_conn_id=conn.id
        )

    async def _hanlde_leave_room(self,conn:Connection,data:dict):
        room_id=data.get("room_id")
        self.manager.leave_room(conn=conn,room_id=room_id)

        await conn.send(message=make_msg(
            msg_type=WSMessageType.ROOM_LEFT,
            room_id=room_id
        ))

        await self.manager.broadcast_to_room(
            room_id=room_id,
            message=make_msg(
                msg_type=WSMessageType.USER_LEFT,
                room_id=room_id,
                username=conn.username
            )
        )

    async def _handle_typing(self,conn:Connection,data:dict):
        room_id=data.get("room_id","general")
        await self.manager.broadcast_to_room(
            room_id=room_id,
            message=make_msg(
                msg_type=WSMessageType.TYPING_IND,
                username=conn.username,
                room_id=room_id,
            ),
            exclude_conn_id=conn.id
        )

    async def _handle_ping(self,conn:Connection,data:dict):
        await conn.send(message=make_msg(WSMessageType.PING))

    async def _handle_disconnect(self,conn:Connection):
        rooms=list(conn.rooms)
        self.manager.disconnect(conn=conn)

        for room_id in rooms:
            await self.manager.broadcast_to_room(
                room_id=room_id,
                message=make_msg(
                    msg_type=WSMessageType.USER_LEFT,
                    room_id=room_id,
                    username=conn.username
                )
            )


    async def _route(self,conn:Connection,data:dict):
        """Route message to correct handler"""
        msg_type=data.get("type")
        handlers={
            WSMessageType.CHAT:self._handle_chat,
            WSMessageType.JOIN_ROOM:self._handle_join_room,
            WSMessageType.LEAVE_ROOM:self._hanlde_leave_room,
            WSMessageType.TYPING:self._handle_typing,
            WSMessageType.PING:self._handle_ping
        }

        handler=handlers.get(msg_type)
        if handler:
            await handler(conn,data)
        else:
            await conn.send(message=make_msg(
                msg_type=WSMessageType.ERROR,
                message=f"Unknown message type {msg_type}"
            ))
    
    async def handle_connection(self,conn:Connection):
        """Main loop — routes each message to the right handler"""
        
        # Auto-join general room
        room=self.manager.join_room(conn=conn,room_id="general")
        await conn.send(message=make_msg(
            msg_type=WSMessageType.WELCOME,
            username=conn.username,
            role=conn.role,
            rooms=self.manager.list_rooms(),
            onine_users=self.manager.get_online_users(),
            hsitory=room.get_history() if room else []
        ))

        # Notify general room
        await self.manager.broadcast_to_room(
            room_id="general",
            message=make_msg(
                msg_type=WSMessageType.USER_JOINED,
                username=conn.username,
                room_id="general",
                online_count=len(self.manager.get_online_users())
            ),
            exclude_conn_id=conn.id
        )

        try:
            while True:
                data=await conn.websocket.receive_json()
                await self._route(conn=conn,data=data)
        except WebSocketDisconnect:
            await self._handle_disconnect(conn=conn)
        except Exception as e:
            print(f"[WS] Error for {conn.username}: {e}")
            await self._handle_disconnect(conn=conn)

chat_handler=ChatHandler(manager=chat_manager)