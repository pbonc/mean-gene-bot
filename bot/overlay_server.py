import os
import asyncio
from aiohttp import web

overlay_clients = set()
_runner = None
_loop = None

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    overlay_clients.add(ws)
    try:
        async for msg in ws:
            pass  # No processing yet
    finally:
        overlay_clients.discard(ws)
    return ws

async def index(request):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, "overlay_static")
    return web.FileResponse(os.path.join(STATIC_DIR, "overlay.html"))

def run():
    global _runner, _loop
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, "overlay_static")

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/", STATIC_DIR, show_index=True)

    # Create a new event loop for this thread
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    async def start():
        global _runner
        _runner = web.AppRunner(app)
        await _runner.setup()
        site = web.TCPSite(_runner, "0.0.0.0", 8080)
        await site.start()
        # Keep running forever (or until loop is stopped)
        while True:
            await asyncio.sleep(3600)

    try:
        _loop.run_until_complete(start())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _loop.run_until_complete(shutdown())

async def shutdown():
    global _runner
    if _runner:
        await _runner.cleanup()

# Helper for other modules: broadcast a message to all overlay clients
async def broadcast_overlay_message(message: dict):
    closed_ws = []
    for ws in list(overlay_clients):
        if not ws.closed:
            await ws.send_json(message)
        else:
            closed_ws.append(ws)
    for ws in closed_ws:
        overlay_clients.discard(ws)