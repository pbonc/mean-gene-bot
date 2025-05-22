import asyncio
import websockets

connected_clients = set()

async def ticker_handler(websocket, path):
    print(f"New connection from {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        async for msg in websocket:
            print(f"Received message from client: {msg}")
            pass
    except websockets.ConnectionClosed:
        print("Connection closed")
    finally:
        connected_clients.remove(websocket)
        print(f"Client disconnected: {websocket.remote_address}")


async def send_heartbeat():
    while True:
        if connected_clients:
            message = "Ticker update: heartbeat"
            await asyncio.wait([
                asyncio.create_task(client.send(message)) 
                for client in connected_clients
            ])
        await asyncio.sleep(2)  # send update every 2 seconds

async def start_ticker_server():
    server = await websockets.serve(ticker_handler, "0.0.0.0", 8765)
    print("🛰️ WebSocket ticker server started on ws://localhost:8765")
    await send_heartbeat()  # runs forever
