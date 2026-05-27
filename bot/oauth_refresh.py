"""
Twitch OAuth Token Refresh Module

Handles automatic token refresh when Twitch access tokens expire.
"""
import os
import requests
import json
from dotenv import load_dotenv, set_key
import logging


def _normalize_access_token(access_token: str | None) -> str:
    if not access_token:
        return ""
    return str(access_token).replace("oauth:", "").strip()

def refresh_twitch_token():
    """
    Refresh the Twitch OAuth token using the refresh token.
    Updates the .env file with the new token.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    load_dotenv()
    
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    refresh_token = os.getenv("TWITCH_REFRESH_TOKEN")
    
    if not all([client_id, client_secret, refresh_token]):
        return False, "Missing required OAuth credentials in .env file"
    
    # Twitch token refresh endpoint
    url = "https://id.twitch.tv/oauth2/token"
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    try:
        print("[OAUTH] Attempting to refresh Twitch access token...")
        response = requests.post(url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        
        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token")
        
        if not new_access_token:
            return False, "No access token in refresh response"
        
        # Update .env file with new tokens
        env_path = ".env"
        if os.path.exists(env_path):
            set_key(env_path, "TWITCH_OAUTH_TOKEN", new_access_token)
            if new_refresh_token:
                set_key(env_path, "TWITCH_REFRESH_TOKEN", new_refresh_token)
            
            print("[OAUTH] Successfully refreshed and updated Twitch access token")
            return True, "Token refreshed successfully"
        else:
            return False, ".env file not found"
            
    except requests.RequestException as e:
        error_msg = f"HTTP error during token refresh: {e}"
        print(f"[OAUTH ERROR] {error_msg}")
        return False, error_msg
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error: {e}"
        print(f"[OAUTH ERROR] {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error during token refresh: {e}"
        print(f"[OAUTH ERROR] {error_msg}")
        return False, error_msg

def validate_twitch_token(access_token):
    """
    Validate a Twitch access token by calling the validation endpoint.
    
    Args:
        access_token (str): The access token to validate
        
    Returns:
        tuple: (valid: bool, message: str)
    """
    access_token = _normalize_access_token(access_token)

    if not access_token:
        return False, "No access token provided"
        
    url = "https://id.twitch.tv/oauth2/validate"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return True, f"Token valid, expires in {data.get('expires_in', 'unknown')} seconds"
        elif response.status_code == 401:
            return False, "Token is invalid or expired"
        else:
            return False, f"Validation failed with status {response.status_code}"
    except Exception as e:
        return False, f"Error validating token: {e}"


def get_twitch_token_details(access_token):
    """Return raw Twitch validate payload for diagnostics."""
    access_token = _normalize_access_token(access_token)
    if not access_token:
        return False, "No access token provided"

    url = "https://id.twitch.tv/oauth2/validate"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return False, f"Validation failed with status {response.status_code}"
        return True, response.json()
    except Exception as e:
        return False, f"Error reading token details: {e}"

def auto_refresh_if_needed():
    """
    Check if the current token is valid, and refresh if needed.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    load_dotenv()
    current_token = _normalize_access_token(os.getenv("TWITCH_OAUTH_TOKEN"))
    
    if not current_token:
        return False, "No TWITCH_OAUTH_TOKEN found in .env"
    
    # Validate current token
    valid, msg = validate_twitch_token(current_token)
    
    if valid:
        print(f"[OAUTH] Current token is valid: {msg}")
        return True, f"Token already valid: {msg}"
    
    print(f"[OAUTH] Current token invalid: {msg}")
    print("[OAUTH] Attempting automatic refresh...")
    
    # Try to refresh
    success, refresh_msg = refresh_twitch_token()
    
    if success:
        # Reload environment to get new token
        load_dotenv(override=True)
        new_token = _normalize_access_token(os.getenv("TWITCH_OAUTH_TOKEN"))
        
        # Validate new token
        new_valid, new_msg = validate_twitch_token(new_token)
        if new_valid:
            return True, f"Token refreshed and validated: {new_msg}"
        else:
            return False, f"Refreshed token is invalid: {new_msg}"
    else:
        return False, f"Failed to refresh token: {refresh_msg}"

if __name__ == "__main__":
    # CLI usage
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        success, message = refresh_twitch_token()
        print(message)
        sys.exit(0 if success else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "validate":
        load_dotenv()
        token = os.getenv("TWITCH_OAUTH_TOKEN")
        valid, message = validate_twitch_token(token)
        print(message)
        sys.exit(0 if valid else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "auto":
        success, message = auto_refresh_if_needed()
        print(message)
        sys.exit(0 if success else 1)
    else:
        print("Usage:")
        print("  python -m bot.oauth_refresh refresh   - Force refresh token")
        print("  python -m bot.oauth_refresh validate  - Validate current token") 
        print("  python -m bot.oauth_refresh auto      - Auto refresh if needed")
