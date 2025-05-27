import os
import requests
import webbrowser
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
REDIRECT_URI = "https://localhost"
SCOPES = ["chat:read", "chat:edit"]

# === 🌐 Build the authorization URL ===
params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": " ".join(SCOPES),
    "access_type": "offline",  # <-- Important for refresh token
    "force_verify": "true"
}

auth_url = f"https://id.twitch.tv/oauth2/authorize?{urlencode(params)}"

print("\n🔗 Please visit this URL to authorize:")
print(auth_url)

# === ✅ Try to open it in Firefox ===
try:
    firefox_path = "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
    webbrowser.get(firefox_path + " %s").open(auth_url)
except webbrowser.Error:
    print("⚠️ Firefox not found. Open manually:\n", auth_url)

# === 📥 Exchange the code for tokens ===
print("\nAfter authorizing, you'll be redirected to:")
print("https://localhost/?code=YOUR_CODE_HERE")
code = input("Paste the code from the URL here: ").strip()

token_url = "https://id.twitch.tv/oauth2/token"
payload = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": code,
    "grant_type": "authorization_code",
    "redirect_uri": REDIRECT_URI,
}

print("\n🔄 Requesting access token...")
resp = requests.post(token_url, data=payload)
data = resp.json()

if "access_token" in data:
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token")

    print(f"\n✅ Access Token:\noauth:{access_token}\n")
    if refresh_token:
        print(f"♻️  Refresh Token:\n{refresh_token}\n")

    print("🔐 Add to your .env:")
    print(f"TWITCH_TOKEN=oauth:{access_token}")
    if refresh_token:
        print(f"TWITCH_REFRESH_TOKEN={refresh_token}")
else:
    print(f"\n❌ Failed to get token: {data}")
