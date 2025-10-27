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
    except Exception as e:
        import logging
        logging.error(f"[WS] Exception in websocket_handler: {e}")
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


# Store the most recent ticker message
latest_ticker_message = "Welcome to the Darmunist News Network."

async def as_overlay_task():
    logging.basicConfig(level=logging.INFO)
    import time
    import random
    from bot.labels_stats import get_ticker_on_deck
    while True:
        try:
            now = time.time()
            logging.info(f"[TICKER DEBUG] Broadcast at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}, clients: {len(as_overlay_clients)}")
            ticker_messages = get_ticker_on_deck()
            # Pick one singular message (random or first)
            if ticker_messages and isinstance(ticker_messages, list) and len(ticker_messages) > 0:
                singular_message = random.choice(ticker_messages)
            else:
                singular_message = "Welcome to the Darmunist News Network."
            # Send the same message as AFK overlay (afk_ticker)
            if as_overlay_clients:
                for ws in list(as_overlay_clients):
                    if not ws.closed:
                        await ws.send_json({"type": "as_overlay_message", "message": singular_message})
                    else:
                        as_overlay_clients.discard(ws)
            else:
                logging.info("[TICKER DEBUG] No overlay clients connected.")
        except Exception as e:
            logging.error(f"[TICKER] Exception in overlay task: {e}")
        await asyncio.sleep(5)

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
