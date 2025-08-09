import os
from aiohttp import web
import asyncio

overlay_clients = set()
_runner = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "overlay_static")

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