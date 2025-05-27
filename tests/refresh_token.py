import os
import requests
from dotenv import load_dotenv

# Get root directory (2 levels up from this file)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load existing .env values
load_dotenv(ENV_PATH)
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")

token_url = "https://id.twitch.tv/oauth2/token"
payload = {
    "grant_type": "refresh_token",
    "refresh_token": REFRESH_TOKEN,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
}

print("🔄 Refreshing access token...")
resp = requests.post(token_url, data=payload)
data = resp.json()

if "access_token" in data:
    access_token = data["access_token"]
    new_refresh_token = data.get("refresh_token")

    print(f"\n✅ New Access Token:\noauth:{access_token}\n")
    print(f"♻️  New Refresh Token:\n{new_refresh_token}\n")

    # Read, update, and write back to .env
    with open(ENV_PATH, "r") as f:
        lines = f.readlines()

    with open(ENV_PATH, "w") as f:
        for line in lines:
            if line.startswith("TWITCH_TOKEN="):
                f.write(f"TWITCH_TOKEN=oauth:{access_token}\n")
            elif line.startswith("TWITCH_REFRESH_TOKEN="):
                f.write(f"TWITCH_REFRESH_TOKEN={new_refresh_token}\n")
            else:
                f.write(line)

    print(f"✅ .env file updated at: {ENV_PATH}")

else:
    print(f"\n❌ Failed to refresh token: {data}")
