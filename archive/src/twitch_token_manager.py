import requests
import json
import os

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

def load_tokens(token_path):
    with open(token_path, "r") as f:
        return json.load(f)

def save_tokens(token_path, tokens):
    with open(token_path, "w") as f:
        json.dump(tokens, f, indent=2)

def validate_token(access_token):
    headers = {"Authorization": f"OAuth {access_token}"}
    resp = requests.get(TWITCH_VALIDATE_URL, headers=headers)
    return resp.status_code == 200, resp.json() if resp.status_code == 200 else resp.text

def refresh_token(client_id, client_secret, refresh_token):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = requests.post(TWITCH_TOKEN_URL, data=data)
    if resp.status_code == 200:
        return resp.json()
    else:
        return None

def ensure_valid_token(token_path, client_id, client_secret):
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"Token file not found: {token_path}")
    tokens = load_tokens(token_path)
    access_token = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    valid, info = validate_token(access_token)
    if valid:
        return access_token
    if not refresh:
        raise Exception("No refresh token available. Bot cannot authenticate.")
    new_tokens = refresh_token(client_id, client_secret, refresh)
    if not new_tokens:
        raise Exception("Failed to refresh token. Stopping.")
    tokens.update({
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens.get("refresh_token", refresh),
        "scope": new_tokens.get("scope"),
    })
    save_tokens(token_path, tokens)
    valid, info = validate_token(tokens["access_token"])
    if not valid:
        raise Exception(f"New access token is still invalid: {info}")
    return tokens["access_token"]