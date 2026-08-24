async def tetris_cards_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "tetris_cards_overlay.html"))
import os
import json
from collections import OrderedDict
from aiohttp import web
import asyncio
from bot.grid_state import GridManager

overlay_clients = set()
# Track clients that want AS_overlay messages
as_overlay_clients = set()
wotwom_chatters = OrderedDict()
_runner = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "overlay_static")
GIFS_DIR = os.path.join(STATIC_DIR, "gifs")
CARDS_DIR = os.path.join(os.path.dirname(BASE_DIR), "assets", "cards")
WHEEL_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(STATIC_DIR)), "data", "wheel_state.json")
RPG_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(STATIC_DIR)), "data", "rpg_state.json")
RPG_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(STATIC_DIR)), "data", "rpg_log.json")

def _load_wheel_state_file():
    if os.path.exists(WHEEL_STATE_FILE):
        try:
            with open(WHEEL_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return {}
    return {}

def _save_wheel_state_file(data: dict):
    try:
        with open(WHEEL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _wheel_payload_from_file():
    data = _load_wheel_state_file()
    slots = {k: int(v) for k, v in data.get("slots", {}).items() if int(v) > 0}
    scores = {k: int(v) for k, v in data.get("scores", {}).items() if int(v) >= 0}
    order = [u for u in data.get("order", []) if u in slots]
    for u in sorted(slots.keys()):
        if u not in order:
            order.append(u)
    colors = {k: v for k, v in data.get("colors", {}).items() if isinstance(v, str)}
    slots_payload = [
        {"name": name, "count": int(slots[name]), "color": colors.get(name)}
        for name in order
    ]
    scores_payload = [
        {"name": name, "score": int(score)}
        for name, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    ]
    total_slots = sum(int(c) for c in slots.values())
    return {
        "type": "wheel_state",
        "slots": slots_payload,
        "scores": scores_payload,
        "total_slots": total_slots,
        "last_winner": data.get("last_winner"),
        "remove_on_win": bool(data.get("remove_on_win", False)),
        "wheel_locked": bool(data.get("wheel_locked", False)),
        "last_man_standing": bool(data.get("last_man_standing", False)),
    }

def _load_rpg_payload_from_files():
    try:
        if not os.path.exists(RPG_STATE_FILE) or not os.path.exists(RPG_LOG_FILE):
            return None
        with open(RPG_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        with open(RPG_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
        session = state.get("session", {})
        users = state.get("users", {})
        party = []
        for idx, username in enumerate(session.get("participants", []), start=1):
            user = users.get(username, {})
            class_name = user.get("class_name", "Derp Clone")
            if user.get("is_revenant"):
                class_name = "Revenant"
            hp_max = int(user.get("hp_max", 10) or 10)
            hp = int(user.get("hp_current", hp_max) or hp_max)
            hp = max(0, min(hp, hp_max))
            party.append({
                "number": idx,
                "name": username,
                "class": class_name,
                "hp": hp,
                "hp_max": hp_max,
                "is_totem": False,
                "is_imp": False,
                "is_undead": False,
                "is_pet": False,
                "goldrpg_ready": bool(user.get("hop_goldrpg_ready")),
                "special_ready": False,
                "special_icon": None,
                "donut_buff_active": False,
                "gold_glow": False,
            })

            # Add any prince summons owned by this participant so fallback payloads still show them
            for summon in session.get("prince_summons", []):
                if str(summon.get("owner", "")).lower() != str(username).lower():
                    continue
                if not summon.get("alive"):
                    continue
                summon_hp_max = int(summon.get("max_hp", 1) or 1)
                summon_hp = int(summon.get("hp", summon_hp_max) or summon_hp_max)
                summon_hp = max(0, min(summon_hp, summon_hp_max))
                party.append({
                    "number": None,
                    "name": f"{username}'s {str(summon.get('type', 'Prince')).title()}",
                    "class": str(summon.get("type", "Prince")).title(),
                    "hp": summon_hp,
                    "hp_max": summon_hp_max,
                    "is_totem": False,
                    "is_imp": False,
                    "is_undead": False,
                    "is_pet": True,
                })
        return {
            "type": "rpg_state",
            "battle_active": bool(session.get("battle_active")),
            "battle_id": session.get("battle_id"),
            "turn_number": session.get("turn_number"),
            "phase": session.get("phase"),
            "action_window_end": session.get("action_window_end"),
            "join_window_end": session.get("join_window_end"),
            "participants": session.get("participants", []),
            "monsters": session.get("monsters", []),
            "party": party,
            "daily_log": log.get("daily_log", []),
            "battle_log": log.get("battle_log", []),
        }
    except Exception:
        return None

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
                    if data.get('type') == 'request_wheel_state':
                        payload = latest_wheel_state or _wheel_payload_from_file()
                        if payload:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                    if data.get('type') == 'request_rpg_state':
                        payload = latest_rpg_state or _load_rpg_payload_from_files()
                        if payload:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                    if data.get('type') == 'request_rpg_v2_expedition':
                        if latest_rpg_v2_expedition:
                            try:
                                await ws.send_json(latest_rpg_v2_expedition)
                            except Exception:
                                pass
                    if data.get('type') == 'request_rpg_v2_battle':
                        if latest_rpg_v2_battle:
                            try:
                                await ws.send_json(latest_rpg_v2_battle)
                            except Exception:
                                pass
                    if data.get('type') == 'request_grid_state':
                        payload = latest_grid_state
                        if not payload:
                            try:
                                payload = GridManager().get_payload()
                            except Exception:
                                payload = None
                        if payload:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                    if data.get('type') == 'request_bittleships_state':
                        payload = latest_bittleships_state
                        if not payload:
                            try:
                                from bot.bittleships_state import BittleshipsManager
                                payload = BittleshipsManager().public_payload()
                            except Exception:
                                payload = None
                        if payload:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                    if data.get('type') == 'request_giveaway_state':
                        payload = latest_giveaway_state
                        if not payload:
                            try:
                                from bot.giveaway_state import GiveawayState
                                payload = GiveawayState().payload()
                            except Exception:
                                payload = None
                        if payload:
                            try:
                                await ws.send_json(payload)
                            except Exception:
                                pass
                    if data.get('type') == 'request_fishing_state':
                        try:
                            from bot.fishing.service import get_fishing_service
                            await ws.send_json(await get_fishing_service().snapshot())
                        except Exception:
                            pass
                    if data.get('type') == 'request_coup_state':
                        try:
                            from bot.coup_service import get_coup_service
                            await ws.send_json(get_coup_service().snapshot())
                        except Exception:
                            pass
                    if data.get('type') == 'request_wotwom_chat_roster':
                        try:
                            await ws.send_json(
                                {
                                    "type": "wotwom_chat_roster",
                                    "usernames": list(wotwom_chatters.values()),
                                }
                            )
                        except Exception:
                            pass
                    if data.get('type') == 'wheel_control':
                        action = data.get('action')
                        if action in ("set_multiplier", "set_remove_on_win"):
                            state = _load_wheel_state_file()
                            state.setdefault("slots", {})
                            state.setdefault("scores", {})
                            if action == "set_multiplier":
                                try:
                                    multiplier = int(data.get("value"))
                                except Exception:
                                    multiplier = 1
                                if multiplier < 1:
                                    multiplier = 1
                                if multiplier > 500:
                                    multiplier = 500
                                if state["slots"]:
                                    state["slots"] = {k: multiplier for k in state["slots"].keys()}
                            if action == "set_remove_on_win":
                                state["remove_on_win"] = bool(data.get("value", True))
                            _save_wheel_state_file(state)
                            await broadcast_overlay_message(_wheel_payload_from_file())
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

async def coup_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "coup_overlay.html"))

async def get_coup_state(request):
    from bot.coup_service import get_coup_service
    return web.json_response(get_coup_service().snapshot())

async def cards_afk_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "cards_afk_overlay.html"))

async def raffle_numbers_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "raffle_numbers.html"))

async def giveaway_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "giveaway_overlay.html"))

async def as_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "as_overlay.html"))

async def anime_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "anime_overlay.html"))

async def allen_ginter_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "allen_ginter_overlay.html"))

async def nfl_break_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "nfl_break_overlay.html"))

async def nba_break_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "nba_break_overlay.html"))

async def nhl_break_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "nhl_break_overlay.html"))

async def mlb_break_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "mlb_break_overlay.html"))

async def wheel_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "wheel_overlay.html"))

async def battle_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "battle_overlay.html"))

async def rpg_micro_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "rpg_micro", "index.html"))

async def rpg_battle_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "rpg_battle", "index.html"))

async def grid_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "grid_overlay.html"))

async def bittleships_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "bittleships_overlay.html"))

async def wom_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "wom_overlay.html"))

async def wotwom_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "wotwom_overlay.html"))

async def fishing_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "fishing_overlay.html"))

async def fishing_afk_overlay(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "fishing_afk_overlay.html"))

async def get_wotwom_inventory(request):
    """Return server-side normalized WoTMA data without exposing the application ID."""
    from bot.wot_api import WotApiError
    from bot.wot_inventory import refresh_wot_snapshot

    try:
        inventory, _ = await refresh_wot_snapshot()
        return web.json_response(inventory)
    except WotApiError as exc:
        return web.json_response({"error": str(exc)}, status=503)
    except Exception:
        logging.exception("[WOTWOM] Unexpected inventory refresh failure")
        return web.json_response(
            {"error": "Unable to load World of Tanks inventory."}, status=500
        )

async def wotwom_auth_start(request):
    """Redirect the local operator to Wargaming's console-service sign in."""
    from bot.wot_api import WotApiClient, WotApiError, WotConfig
    import aiohttp

    redirect_uri = os.getenv(
        "WOT_AUTH_REDIRECT_URI",
        "http://localhost:8080/api/wotwom/auth/callback",
    ).strip()
    try:
        async with aiohttp.ClientSession() as session:
            location = await WotApiClient(
                WotConfig.from_env(), session
            ).login_url(redirect_uri)
        raise web.HTTPFound(location)
    except web.HTTPFound:
        raise
    except WotApiError as exc:
        return web.Response(text=str(exc), status=503)

async def wotwom_auth_callback(request):
    """Persist the private token returned by console authorization."""
    from bot.wot_api import WotApiError, save_wot_auth

    payload = dict(request.query)
    if payload.get("status") == "error" or payload.get("error"):
        return web.Response(
            text="World of Tanks authorization was cancelled or denied.",
            status=400,
        )
    try:
        save_wot_auth(payload)
    except WotApiError as exc:
        return web.Response(text=str(exc), status=400)
    return web.Response(
        content_type="text/html",
        text=(
            "<!doctype html><title>WoTWoM Authorized</title>"
            "<body style='background:#07170a;color:#83ff7d;font:20px monospace;"
            "display:grid;place-items:center;min-height:100vh'>"
            "<div><h1>GARAGE LINK AUTHORIZED</h1>"
            "<p>The access token was stored locally. You may close this tab.</p></div>"
            "</body>"
        ),
    )

async def get_wotwom_auth_status(request):
    from bot.wot_api import load_wot_auth

    auth = load_wot_auth()
    return web.json_response(
        {
            "authorized": bool(auth.get("access_token")),
            "account_id": auth.get("account_id"),
            "nickname": auth.get("nickname"),
            "expires_at": auth.get("expires_at"),
        }
    )

async def post_wotwom_result(request):
    from bot.wot_operations import record_operation

    try:
        payload = await request.json()
        result = record_operation(payload)
        return web.json_response({"ok": True, "result": result})
    except (ValueError, json.JSONDecodeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)

async def get_wotwom_sold(request):
    from bot.wot_sold import sold_vehicles

    return web.json_response({"vehicles": sold_vehicles()})

async def post_wotwom_sold(request):
    from bot.wot_sold import mark_sold, restore_vehicle, sold_vehicles

    try:
        payload = await request.json()
        action = str(payload.get("action") or "").lower()
        if action == "sold":
            result = mark_sold(payload.get("vehicle") or {})
        elif action == "restore":
            result = {"restored": restore_vehicle(int(payload["tank_id"]))}
        else:
            raise ValueError("Unknown sold-status action.")
        return web.json_response(
            {"ok": True, "result": result, "vehicles": sold_vehicles()}
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)

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
    
    cards_dir = CARDS_DIR
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
latest_wheel_state = None
latest_rpg_state = None
latest_rpg_v2_expedition = None
latest_rpg_v2_battle = None
latest_grid_state = None
latest_bittleships_state = None
latest_giveaway_state = None


async def rpg_state_task(interval: float = 2.0):
    """Periodic safety broadcast of the latest RPG state to keep battle overlays in sync."""
    global latest_rpg_state
    while True:
        try:
            payload = latest_rpg_state or _load_rpg_payload_from_files()
            if payload and payload.get("type") == "rpg_state":
                # Only broadcast if there is an active/ongoing context to reduce noise.
                if payload.get("battle_active") or payload.get("participants") or payload.get("monsters"):
                    await broadcast_overlay_message(payload)
        except Exception:
            logging.warning("[OVERLAY] rpg_state_task failed", exc_info=True)
        await asyncio.sleep(max(0.5, interval))

async def as_overlay_task():
    import time
    import random
    # This task sends the latest full ticker string (as produced by main.ticker_cycle_task)
    # to AS overlay clients at a regular interval. It does NOT build the ticker itself
    # to avoid diverging formatting or ordering.
    while True:
        try:
            now = time.time()
            logging.debug(f"[TICKER DEBUG] Broadcast at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}, clients: {len(as_overlay_clients)}")
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
    global latest_ticker_message, latest_wheel_state, latest_rpg_state, latest_rpg_v2_expedition, latest_rpg_v2_battle, latest_grid_state, latest_bittleships_state, latest_giveaway_state
    if message.get("type") == "ticker" and "text" in message:
        latest_ticker_message = message["text"]
    if message.get("type") == "wheel_state":
        latest_wheel_state = message
    if message.get("type") == "rpg_state":
        latest_rpg_state = message
    if message.get("type") == "rpg_v2_expedition":
        latest_rpg_v2_expedition = message
    if message.get("type") == "rpg_v2_battle_snapshot":
        latest_rpg_v2_battle = message
    if message.get("type") == "grid_state":
        latest_grid_state = message
    if message.get("type") == "bittleships_state":
        latest_bittleships_state = message
    if message.get("type") == "giveaway_state":
        latest_giveaway_state = message
    if message.get("type") == "wotwom_chat_user":
        username = str(message.get("username") or "").strip()
        if username:
            key = username.casefold()
            wotwom_chatters.pop(key, None)
            wotwom_chatters[key] = username
            while len(wotwom_chatters) > 100:
                wotwom_chatters.popitem(last=False)
    
    msg_type = message.get("type", "unknown")
    logging.debug(f"Broadcasting {msg_type} message to {len(overlay_clients)} overlay clients")

    for ws in list(overlay_clients):
        if ws.closed:
            overlay_clients.discard(ws)
            continue
        try:
            await ws.send_json(message)
        except Exception:
            # Drop clients that error so future broadcasts succeed without refreshes
            overlay_clients.discard(ws)
            logging.warning("[OVERLAY] Dropped overlay client due to send failure", exc_info=True)

async def start_overlay_server(host: str = "0.0.0.0", port: int = 8080):
    """Start the aiohttp overlay server and ticker broadcast task."""
    app = web.Application()
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/", index)
    app.router.add_get("/afk", afk_overlay)
    app.router.add_get("/cards", cards_afk_overlay)
    app.router.add_get("/raffle", raffle_numbers_overlay)
    app.router.add_get("/giveaway", giveaway_overlay)
    app.router.add_get("/as", as_overlay)
    app.router.add_get("/anime", anime_overlay)
    app.router.add_get("/ag", allen_ginter_overlay)
    app.router.add_get("/nfl", nfl_break_overlay)
    app.router.add_get("/nba", nba_break_overlay)
    app.router.add_get("/nhl", nhl_break_overlay)
    app.router.add_get("/mlb", mlb_break_overlay)
    app.router.add_get("/wheel", wheel_overlay)
    app.router.add_get("/battle", battle_overlay)
    app.router.add_get("/rpg-micro", rpg_micro_overlay)
    app.router.add_get("/rpg-battle", rpg_battle_overlay)
    app.router.add_get("/grid", grid_overlay)
    app.router.add_get("/bittleships", bittleships_overlay)
    app.router.add_get("/wom", wom_overlay)
    app.router.add_get("/wotwom", wotwom_overlay)
    app.router.add_get("/fishing", fishing_overlay)
    app.router.add_get("/fishing-afk", fishing_afk_overlay)
    app.router.add_get("/election-central", coup_overlay)

    # Tetris card drop overlay
    app.router.add_get("/tetris", tetris_cards_overlay)
    
    # API routes
    app.router.add_get("/api/cards", get_card_data)
    app.router.add_get("/api/raffle", get_raffle_data)
    app.router.add_get("/api/coup", get_coup_state)
    app.router.add_get("/api/wotwom/inventory", get_wotwom_inventory)
    app.router.add_get("/api/wotwom/auth/start", wotwom_auth_start)
    app.router.add_get("/api/wotwom/auth/callback", wotwom_auth_callback)
    app.router.add_get("/api/wotwom/auth/status", get_wotwom_auth_status)
    app.router.add_post("/api/wotwom/results", post_wotwom_result)
    app.router.add_get("/api/wotwom/sold", get_wotwom_sold)
    app.router.add_post("/api/wotwom/sold", post_wotwom_sold)
    # Serve GIFs and other overlay static assets
    gifs_dir = GIFS_DIR
    if os.path.isdir(gifs_dir):
        app.router.add_static('/gifs', gifs_dir)

    rpg_micro_dir = os.path.join(STATIC_DIR, "rpg_micro")
    if os.path.isdir(rpg_micro_dir):
        app.router.add_static('/rpg-micro-assets', rpg_micro_dir)

    rpg_battle_dir = os.path.join(STATIC_DIR, "rpg_battle")
    if os.path.isdir(rpg_battle_dir):
        app.router.add_static('/rpg-battle-assets', rpg_battle_dir)

    bittleships_audio_dir = os.path.join(STATIC_DIR, "bittleships_audio")
    if os.path.isdir(bittleships_audio_dir):
        app.router.add_static('/bittleships_audio', bittleships_audio_dir)
    wom_audio_dir = os.path.join(STATIC_DIR, "wom_audio")
    if os.path.isdir(wom_audio_dir):
        app.router.add_static('/wom_audio', wom_audio_dir)
    fishing_assets_dir = os.path.join(STATIC_DIR, "fishing")
    if os.path.isdir(fishing_assets_dir):
        app.router.add_static('/fishing-assets', fishing_assets_dir)
    
    # Serve trading card images
    cards_dir = CARDS_DIR
    if os.path.isdir(cards_dir):
        app.router.add_static('/cards', cards_dir)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info(f"[OVERLAY] Server started at http://{host}:{port}")
    # Start ticker broadcast task
    asyncio.create_task(as_overlay_task())
    asyncio.create_task(rpg_state_task())
    # Keep running forever
    while True:
        await asyncio.sleep(3600)
