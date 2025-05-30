import asyncio
import websockets
import json
import traceback
import logging

print("WS_SERVER: src/backend/ws_server.py loaded!")

# Configure logging for more informative output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s'
)

print("Correct ws_server.py loaded!")  # Confirm file is loaded

connected = set()

async def handler(websocket, path):
    logging.info("Handler called with: %s %s", websocket, path)
    connected.add(websocket)
    try:
        logging.info("Handler has entered try block, waiting for messages...")
        async for message in websocket:
            logging.debug("Received from client: %s", message)
            # echo for debug
            await websocket.send("pong")
    except Exception as e:
        logging.error("Exception in handler: %s", e)
        logging.error(traceback.format_exc())  # Full stack trace
    finally:
        logging.info("WebSocket disconnecting: %s", websocket)
        connected.remove(websocket)

async def run_ws_server():
    logging.info("Starting Overlay WS server...")
    server = await websockets.serve(handler, "localhost", 6789)
    print("Overlay WS server started at ws://localhost:6789")
    await server.wait_closed()

def start_ws_server_threaded():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_ws_server())

async def broadcast_overlay_message(payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload)
    if connected:
        await asyncio.wait([ws.send(payload) for ws in connected])