import os
from aiohttp import web
import asyncio

overlay_clients = set()
# Track clients that want AS_overlay messages
as_overlay_clients = set()
_runner = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "overlay_static")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    overlay_clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    import json
                    data = json.loads(msg.data)
                    if data.get('type') == 'as_overlay_subscribe':
                        as_overlay_clients.add(ws)
                except Exception:
                    pass
    finally:
        overlay_clients.discard(ws)
        as_overlay_clients.discard(ws)
    return ws

async def index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "overlay.html"))

async def start_overlay_server():
    global _runner

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/", STATIC_DIR, show_index=True)

    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, "0.0.0.0", 8080)
    await site.start()
    # No print here!
    # print("Overlay server running at http://localhost:8080/")

    # Start AS_overlay message task
    async def as_overlay_task():
        import random
        import time
        from bot.labels_stats import get_ticker_messages
        while True:
            try:
                # Only send if there are clients
                if as_overlay_clients:
                    msgs = await get_ticker_messages()
                    if msgs:
                        msg = random.choice(msgs)
                        for ws in list(as_overlay_clients):
                            if not ws.closed:
                                await ws.send_json({"type": "as_overlay_message", "message": msg})
                            else:
                                as_overlay_clients.discard(ws)
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(10)
    asyncio.create_task(as_overlay_task())

async def shutdown():
    global _runner
    if _runner:
        await _runner.cleanup()

# No print/logging here!
async def broadcast_overlay_message(message: dict):
    closed_ws = []
    for ws in list(overlay_clients):
        if not ws.closed:
            await ws.send_json(message)
        else:
            closed_ws.append(ws)
    for ws in closed_ws:
        overlay_clients.discard(ws)

if __name__ == "__main__":
    async def main():
        await start_overlay_server()
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await shutdown()
    asyncio.run(main())