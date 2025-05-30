# Basic overlay WebSocket server
import asyncio
import websockets

connected = set()

async def handler(websocket, path):
    connected.add(websocket)
    try:
        async for _ in websocket:
            pass  # Overlay clients don't send messages
    finally:
        connected.remove(websocket)

async def run_ws_server():
    server = await websockets.serve(handler, "localhost", 6789)
    print("Overlay WS server started at ws://localhost:6789")
    await server.wait_closed()

# Allows import as module for threading/asyncio
def start_ws_server_threaded():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_ws_server())

# For sending overlay commands from anywhere in your bot:
async def broadcast_overlay_message(msg: str):
    if connected:
        await asyncio.wait([ws.send(msg) for ws in connected])

# Optionally: add helper functions for ticker/image here