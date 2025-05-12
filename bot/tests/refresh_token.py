import os
import requests
from dotenv import load_dotenv

# Load client and refresh values
load_dotenv()
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
    print("🔐 Update your .env file with:")
    print(f"TWITCH_TOKEN=oauth:{access_token}")
    print(f"TWITCH_REFRESH_TOKEN={new_refresh_token}")
else:
    print(f"\n❌ Failed to refresh token: {data}")