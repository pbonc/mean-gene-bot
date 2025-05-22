import asyncio
import json
import os
from pathlib import Path
import websockets

WRESTLERS_PATH = Path(__file__).parent.parent.parent / "dwf" / "wrestlers.json"
LABELS_PATH = Path(__file__).parent.parent.parent / "labels"

TICKER_INTERVAL = 10  # seconds

async def build_ticker_messages():
    messages = []

    # --- DWF Titleholders ---
    if WRESTLERS_PATH.exists():
        with open(WRESTLERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for wrestler in data:
                # Find all title fields (e.g., "champion": true)
                for key, value in wrestler.items():
                    if key.lower().endswith("champion") and value:
                        title_name = key.replace("_", " ").title()
                        messages.append(f"Current {title_name}: {wrestler.get('name', 'Unknown')}")
                # Or, if you track titles differently, adjust here

    # --- Twitch stats from labels/ ---
    if LABELS_PATH.exists():
        for file in LABELS_PATH.glob("*.txt"):
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    stat = line.strip()
                    if stat:
                        messages.append(stat)

    # --- Add more sources here later (API calls, sports, etc) ---

    if not messages:
        messages = ["Welcome to the Darmunist News Network."]
    return messages

class TickerServer:
    def __init__(self):
        self.clients = set()
        self.messages = []
        self.idx = 0

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"New overlay connected. Total: {len(self.clients)}")

    async def unregister(self, websocket):
        self.clients.remove(websocket)
        print(f"Overlay disconnected. Total: {len(self.clients)}")

    async def handler(self, websocket, path):
        await self.register(websocket)
        try:
            async for _ in websocket:  # We don't expect messages from the overlay client
                pass
        finally:
            await self.unregister(websocket)

    async def ticker_loop(self):
        while True:
            self.messages = await build_ticker_messages()
            if self.messages:
                msg = {
                    "type": "ticker",
                    "text": self.messages[self.idx % len(self.messages)]
                }
                print("Broadcasting:", msg["text"])
                await asyncio.gather(*[ws.send(json.dumps(msg)) for ws in self.clients if ws.open])
                self.idx += 1
            await asyncio.sleep(TICKER_INTERVAL)

    async def main(self):
        server = await websockets.serve(self.handler, "localhost", 6789)
        print("TickerServer WebSocket running on ws://localhost:6789")
        await self.ticker_loop()

if __name__ == "__main__":
    server = TickerServer()
    asyncio.run(server.main())