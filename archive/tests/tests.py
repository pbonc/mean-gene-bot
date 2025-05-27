import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            print("Connected to websocket server!")
            while True:
                msg = await ws.recv()
                print("Received:", msg)
    except Exception as e:
        print("Connection error:", e)

asyncio.run(test())
