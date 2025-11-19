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

async def cards_afk_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "cards_afk_overlay.html"))

async def raffle_numbers_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "raffle_numbers.html"))

async def as_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "as_overlay.html"))

async def anime_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "anime_overlay.html"))

async def get_raffle_data(request):
    """API endpoint to return current raffle state"""
    import json
    import os
    
    try:
        # Load raffle state from the same location as the raffle cog
        raffle_file = os.path.join(os.path.dirname(os.path.dirname(STATIC_DIR)), "data", "raffle_state.json")
        
        if os.path.exists(raffle_file):
            with open(raffle_file, 'r') as f:
                raffle_data = json.load(f)
            return web.json_response(raffle_data)
        else:
            return web.json_response({"error": "Raffle state file not found"})
            
    except Exception as e:
        return web.json_response({"error": str(e)})

async def get_card_data(request):
    """API endpoint to return card data from scanned directory"""
    import json
    import re
    
    cards_dir = os.path.join(os.path.dirname(STATIC_DIR), "assets", "cards")
    card_data = []
    
    if not os.path.isdir(cards_dir):
        return web.json_response({"cards": [], "error": "Cards directory not found"})
    
    # Supported image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    
    try:
        # Scan all files in cards directory (including subdirectories)
        for root, dirs, files in os.walk(cards_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                file_ext = os.path.splitext(filename)[1].lower()
                
                if file_ext in image_extensions:
                    # Parse filename for card info
                    card_info = parse_card_filename(filename, root, cards_dir)
                    if card_info:
                        card_data.append(card_info)
        
        return web.json_response({"cards": card_data})
    
    except Exception as e:
        return web.json_response({"cards": [], "error": str(e)})

def parse_card_filename(filename, file_path, base_cards_dir):
    """
    Parse card filename to extract card information
    Expected formats:
    - player-year-set-grade.jpg (e.g., jordan-1986-fleer-psa9.jpg)
    - player-year-set.jpg (raw card, e.g., gretzky-1979-opc.jpg)
    - Custom formats with hyphens as delimiters
    """
    try:
        # Remove file extension
        name_without_ext = os.path.splitext(filename)[0]
        
        # Split by hyphens
        parts = name_without_ext.split('-')
        
        if len(parts) < 3:
            # Fallback: use filename as player name
            return {
                "name": name_without_ext.replace('-', ' ').title(),
                "year": "Unknown",
                "set": "Unknown", 
                "grade": "Raw",
                "type": "raw-card",
                "rarity": "Unknown",
                "image": get_relative_path(file_path, filename, base_cards_dir)
            }
        
        # Extract basic info
        player = parts[0].replace('_', ' ').title()
        year = parts[1] if len(parts) > 1 else "Unknown"
        set_name = parts[2].replace('_', ' ').title() if len(parts) > 2 else "Unknown"
        
        # Determine grade and type from filename or directory
        grade = "Raw"
        card_type = "raw-card"
        rarity = "Base"
        
        # Check for grade in filename (last part usually)
        if len(parts) >= 4:
            grade_part = parts[-1].lower()
            if 'psa' in grade_part:
                card_type = "psa-slab"
                grade = f"PSA {extract_number(grade_part)}"
            elif 'bgs' in grade_part or 'beckett' in grade_part:
                card_type = "bgs-slab" 
                grade = f"BGS {extract_number(grade_part)}"
            elif 'sgc' in grade_part:
                card_type = "sgc-slab"
                grade = f"SGC {extract_number(grade_part)}"
            else:
                grade = parts[-1].upper()
        
        # Check directory name for card type if not found in filename
        rel_path = os.path.relpath(file_path, base_cards_dir)
        if 'psa' in rel_path.lower():
            card_type = "psa-slab"
        elif 'bgs' in rel_path.lower() or 'beckett' in rel_path.lower():
            card_type = "bgs-slab"
        elif 'sgc' in rel_path.lower():
            card_type = "sgc-slab"
        elif 'raw' in rel_path.lower():
            card_type = "raw-card"
        
        # Detect rarity keywords
        filename_lower = filename.lower()
        if any(word in filename_lower for word in ['rookie', 'rc', 'rook']):
            rarity = "Rookie"
        elif any(word in filename_lower for word in ['auto', 'autograph', 'sig']):
            rarity = "Autograph"
        elif any(word in filename_lower for word in ['patch', 'jersey', 'relic']):
            rarity = "Memorabilia"
        elif any(word in filename_lower for word in ['refractor', 'prizm', 'chrome']):
            rarity = "Parallel"
        
        return {
            "name": player,
            "year": year,
            "set": set_name,
            "grade": grade,
            "type": card_type,
            "rarity": rarity,
            "image": get_relative_path(file_path, filename, base_cards_dir)
        }
        
    except Exception as e:
        # Return basic info if parsing fails
        return {
            "name": os.path.splitext(filename)[0].replace('-', ' ').title(),
            "year": "Unknown",
            "set": "Unknown",
            "grade": "Raw", 
            "type": "raw-card",
            "rarity": "Unknown",
            "image": get_relative_path(file_path, filename, base_cards_dir)
        }

def extract_number(text):
    """Extract number from grade text (e.g., 'psa9' -> '9', 'bgs95' -> '9.5')"""
    import re
    numbers = re.findall(r'\d+', text)
    if numbers:
        num = numbers[0]
        # Handle decimal grades (e.g., 95 -> 9.5)
        if len(num) == 2 and num[1] == '5':
            return f"{num[0]}.5"
        return num
    return "?"

def get_relative_path(file_path, filename, base_dir):
    """Get the relative URL path for the image"""
    full_path = os.path.join(file_path, filename)
    rel_path = os.path.relpath(full_path, base_dir)
    return f"/cards/{rel_path.replace(os.sep, '/')}"

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
    app.router.add_get("/cards", cards_afk_overlay)
    app.router.add_get("/raffle", raffle_numbers_overlay)
    app.router.add_get("/as", as_overlay)
    app.router.add_get("/anime", anime_overlay)
    
    # API routes
    app.router.add_get("/api/cards", get_card_data)
    app.router.add_get("/api/raffle", get_raffle_data)
    # Serve GIFs and other overlay static assets
    gifs_dir = os.path.join(STATIC_DIR, "gifs")
    if os.path.isdir(gifs_dir):
        app.router.add_static('/gifs', gifs_dir)
    
    # Serve trading card images
    cards_dir = os.path.join(os.path.dirname(STATIC_DIR), "assets", "cards")
    if os.path.isdir(cards_dir):
        app.router.add_static('/cards', cards_dir)
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
