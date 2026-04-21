import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

import asyncio
from typing import AsyncGenerator
import json
from datetime import datetime,timezone

class SSENotificationHub:
    """
    SSE hub for clients that want server-push notifications
    without a full WebSocket connection.

    Use cases:
    - Admin dashboard watching real-time stats
    - Notification bell in UI
    - User watching AI processing status
    """
    def __init__(self):
        self._queues:dict[str,asyncio.Queue]={}

    def register(self,client_id:str):
        self._queues[client_id]=asyncio.Queue(maxsize=50)
    
    def unregister(self,client_id:str):
        self._queues.pop(client_id,None)

    async def push(self,client_id:str,event:str,data:dict):
        q=self._queues.get(client_id)
        if q:
            try:
                q.put_nowait({"event":event,"data":data})
            except asyncio.QueueFull:
                pass

    async def broadcast(self,event:str,data:dict):
        for client_id in list(self._queues.keys()):
            await self.push(client_id=client_id,event=event,data=data)

    async def stream(self,client_id:str)->AsyncGenerator[str,None]:
        """Generator that yields SSE-formatted messages"""
        if client_id not in  self._queues:
            self.register(client_id=client_id)

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"

        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        self._queues[client_id].get(),
                        timeout=30.0
                    )
                    yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now(timezone.utc).isoformat()})}\n\n"

        except asyncio.CancelledError:
            self.unregister(client_id)


sse_hub = SSENotificationHub()

