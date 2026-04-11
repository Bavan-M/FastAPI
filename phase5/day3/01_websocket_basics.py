import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,WebSocket,WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json
import asyncio

app=FastAPI(title="WebSocket Basics")

# BASIC WEBSOCKET
@app.websocket("/ws/basic")
async def websocket_basic(websocket:WebSocket):
    # Step 1 — Accept the connection
    await websocket.accept()
    print(f"[WS] Client connected")
    try:
        while True:
            # Step 2 — Receive message from client
            data=await websocket.receive_text()
            print(f"[WS] Received: {data}")

            # Step 3 — Send response back
            await websocket.send_text(data=f"Echo:{data}")

    except WebSocketDisconnect:
         print(f"[WS] Client disconnected")


# SEND DIFFERENT DATA TYPES Text,JSON,File,Image,ect in the chat 
@app.websocket("/ws/types")
async def websocket_types(websocket:WebSocket):
    await websocket.accept()

    try:
        # Send text
        await websocket.send_text("Hello from the server")

        # Send JSON
        await websocket.send_json(data={
            "type":"greeting",
            "message":"Hello",
            "timestamp":123456
        })

        # Send bytes
        await websocket.send_bytes(b"binary data here")

        # Receive and handle different types
        while True:
            # receive_text, receive_json, receive_bytes
            # OR receive() which returns a dict with type info
            message=await websocket.receive()

            if message["type"]=="websocket.disconnect":
                break
            elif message["type"]=="websocket.recieve":
                if "text" in message:
                    data=message["text"]
                    print(f"[WS] Text: {data}")
                    await websocket.send_json(
                        {
                            "recieved":"text",
                            "data":data
                        }
                    )
                elif "bytes" in message:
                    data=message["bytes"]
                    print(f"[WS] Bytes: {len(data)} bytes")
                    await websocket.send_json(
                        {
                            "recieved":"bytes",
                            "size":len(data)
                        }
                    )
    except WebSocketDisconnect:
        print("[WS] Disconnected")

# WEBSOCKET WITH QUERY PARAMS AND PATH PARAMS(like giving tags for every chat coversation to know what and who are asking)
@app.websocket("/ws/chat/{room_id}")
async def websocket_with_param(websocket:WebSocket,room_id:str,username:str="anonymous"):
    await websocket.accept()
    print(f"[WS] {username} joined room {room_id}")

    await websocket.send_json(
        {
            "text":"system",
            "message":f"Welcome {username} to room {room_id}"
        }
    )

    try:
        while True:
            data=await websocket.receive_json()
            print(f"[WS] [{room_id}] {username}: {data}")

            await websocket.send_json({
                "type":"message",
                "room":room_id,
                "from":username,
                "content":data.get("content","")
            })
    except WebSocketDisconnect:
        print(f"[WS] {username} left room {room_id}")

# BIDIRECTIONAL — server pushes AND receives
@app.websocket("/ws/bidirectional")
    # Features your pattern enables:
    # - ✅ Real-time messages
    # - ✅ Typing indicators  
    # - ✅ Read receipts
    # - ✅ Online status
    # - ✅ Last seen
    # - ✅ Delivery confirmations
async def websocket_bidirectional(websocket:WebSocket):
    await websocket.accept()
    
    # Task 1 — receive messages from client
    async def recieve_message():
        try:
            while True:
                data=await websocket.receive_text()
                print(f"[WS] Client says: {data}")
                await websocket.send_json(
                    {
                        "type":"ack",
                        "recieved":data
                    }
                )
        except WebSocketDisconnect:
            pass

    async def push_updates():
        counter=0
        try:
            while True:
                counter+=1
                await websocket.send_json(
                    {
                        "type":"sever_update",
                        "counter":counter,
                        "message":f"Server tick #{counter}"
                    }
                )
                await asyncio.sleep(1)
        except Exception:
            pass
    await asyncio.gather(
        recieve_message(),
        push_updates(),
        return_exceptions=True
    )


@app.get("/", response_class=HTMLResponse)
def test_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            #log { border: 1px solid #ccc; padding: 10px; height: 300px;
                   overflow-y: auto; font-family: monospace; font-size: 13px; }
            button { padding: 8px 16px; margin: 4px; cursor: pointer; }
            input  { padding: 8px; width: 300px; }
            .sent     { color: blue; }
            .received { color: green; }
            .system   { color: orange; }
            .error    { color: red; }
        </style>
    </head>
    <body>
        <h2>🔌 WebSocket Test</h2>

        <div>
            <button onclick="connectBasic()">Connect Basic</button>
            <button onclick="connectBidirectional()">Connect Bidirectional</button>
            <button onclick="disconnect()">Disconnect</button>
        </div>

        <div style="margin: 10px 0;">
            <input id="msg" type="text" placeholder="Type a message..." />
            <button onclick="sendMessage()">Send</button>
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

            function connectBasic() {
                disconnect();
                ws = new WebSocket('ws://localhost:8000/ws/basic');

                ws.onopen = () => addLog('Connected to basic WS', 'system');

                ws.onmessage = (e) => addLog(`← ${e.data}`, 'received');

                ws.onclose = () => addLog('Disconnected', 'system');

                ws.onerror = (e) => addLog(`Error: ${e}`, 'error');
            }

            function connectBidirectional() {
                disconnect();
                ws = new WebSocket('ws://localhost:8000/ws/bidirectional');

                ws.onopen = () => addLog('Connected to bidirectional WS', 'system');

                ws.onmessage = (e) => {
                    const data = JSON.parse(e.data);
                    if (data.type === 'server_update') {
                        addLog(`← Server tick #${data.counter}`, 'received');
                    } else {
                        addLog(`← ${JSON.stringify(data)}`, 'received');
                    }
                };

                ws.onclose = () => addLog('Disconnected', 'system');
            }

            function sendMessage() {
                const msg = document.getElementById('msg').value;
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(msg);
                    addLog(`→ ${msg}`, 'sent');
                    document.getElementById('msg').value = '';
                }
            }

            function disconnect() {
                if (ws) { ws.close(); ws = null; }
            }

            // Send on Enter key
            document.getElementById('msg').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
    </body>
    </html>
    """