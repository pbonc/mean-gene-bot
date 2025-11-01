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
                    # AS overlay subscription (AS overlay pages send this)
                    if data.get('type') == 'as_overlay_subscribe':
                        as_overlay_clients.add(ws)
                    # Standard overlay pages request the latest full ticker
                    # on connect. Respond only to the requesting client so
                    # AS overlay clients do not receive the full ticker.
                    if data.get('type') == 'request_latest_ticker':
                        # Only reply if we have a non-empty canonical ticker to send.
                        if latest_ticker_message and latest_ticker_message.strip():
                            try:
                                await ws.send_json({"type": "ticker", "text": latest_ticker_message})
                            except Exception:
                                pass
                except Exception:
                    pass
    finally:
        overlay_clients.discard(ws)
        as_overlay_clients.discard(ws)
    return ws
import logging

async def index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "overlay.html"))

async def afk_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "afk_overlay.html"))

async def as_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "as_overlay.html"))

async def anime_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "anime_overlay.html"))

async def shutdown():
    global _runner
    if _runner:
        await _runner.cleanup()

# Store the most recent ticker message. Start empty so overlays don't
# receive a welcome/default ticker on connect.
latest_ticker_message = ""

async def as_overlay_task():
    logging.basicConfig(level=logging.INFO)
    import time
    import random
    # This task sends the latest full ticker string (as produced by main.ticker_cycle_task)
    # to AS overlay clients at a regular interval. It does NOT build the ticker itself
    # to avoid diverging formatting or ordering.
    while True:
        try:
            now = time.time()
            logging.info(f"[TICKER DEBUG] Broadcast at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}, clients: {len(as_overlay_clients)}")
            # AS overlay task intentionally does not send ticker messages.
            # AS overlay clients are a separate UI and should not receive the regular
            # ticker payloads (those are sent via broadcast_overlay_message as type 'ticker').
            if as_overlay_clients:
                # For now we simply log connected AS overlay clients; custom AS messages
                # can be implemented here in the future.
                logging.info(f"[AS_OVERLAY] AS clients connected: {len(as_overlay_clients)}")
            else:
                logging.debug("[AS_OVERLAY] No AS overlay clients connected.")
        except Exception as e:
            logging.error(f"[TICKER] Exception in overlay task: {e}")
        await asyncio.sleep(60)

async def broadcast_overlay_message(message: dict):
    """Broadcast a message to all overlay clients (WebSocket). Also update latest ticker message if type is 'ticker'."""
    global latest_ticker_message
    if message.get("type") == "ticker" and "text" in message:
        latest_ticker_message = message["text"]
    for ws in list(overlay_clients):
        if not ws.closed:
            await ws.send_json(message)
        else:
            overlay_clients.discard(ws)

async def start_overlay_server(host: str = "0.0.0.0", port: int = 8080):
    """Start the aiohttp overlay server and ticker broadcast task."""
    app = web.Application()
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/", index)
    app.router.add_get("/afk", afk_overlay)
    app.router.add_get("/as", as_overlay)
    app.router.add_get("/anime", anime_overlay)
    # Serve GIFs and other overlay static assets
    gifs_dir = os.path.join(STATIC_DIR, "gifs")
    if os.path.isdir(gifs_dir):
        app.router.add_static('/gifs', gifs_dir)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info(f"[OVERLAY] Server started at http://{host}:{port}")
    # Start ticker broadcast task
    asyncio.create_task(as_overlay_task())
    # Keep running forever
    while True:
        await asyncio.sleep(3600)
