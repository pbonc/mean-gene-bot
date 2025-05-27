import os
import requests
from dotenv import load_dotenv

def refresh_twitch_token():
    load_dotenv()
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")
    env_path = ".env"

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    token_url = "https://id.twitch.tv/oauth2/token"
    resp = requests.post(token_url, data=payload)
    data = resp.json()
    if "access_token" in data:
        access_token = data["access_token"]
        new_refresh_token = data.get("refresh_token", refresh_token)
        # Update .env
        lines = []
        with open(env_path, "r") as f:
            lines = f.readlines()
        with open(env_path, "w") as f:
            for line in lines:
                if line.startswith("TWITCH_TOKEN="):
                    f.write(f"TWITCH_TOKEN=oauth:{access_token}\n")
                elif line.startswith("TWITCH_REFRESH_TOKEN="):
                    f.write(f"TWITCH_REFRESH_TOKEN={new_refresh_token}\n")
                else:
                    f.write(line)
        print("✅ Refreshed and updated .env with new tokens.")
        return access_token
    else:
        print(f"❌ Could not refresh Twitch token: {data}")
        return None

if __name__ == "__main__":
    refresh_twitch_token()
    # Now launch your bot as usual...