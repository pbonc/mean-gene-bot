#!/usr/bin/env python3
"""
Twitch OAuth Token Generator for Mean Gene Bot

This script helps you get a new OAuth token for your bot account.
"""

import os
import webbrowser
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()


def _get_redirect_uri() -> str:
    """Return redirect URI used for Twitch OAuth authorization."""
    redirect_uri = (os.getenv('TWITCH_REDIRECT_URI') or '').strip()
    if redirect_uri:
        return redirect_uri
    # Keep a localhost default, but make it easy to override in .env.
    return 'http://localhost:3000'

def generate_oauth_url():
    """Generate the OAuth URL for getting a new token"""
    client_id = os.getenv('TWITCH_CLIENT_ID')
    if not client_id:
        print("❌ TWITCH_CLIENT_ID not found in .env file")
        return
    
    # Scopes needed for the bot
    scopes = [
        'chat:read',
        'chat:edit', 
        'whispers:read',
        'whispers:edit',
        'moderator:read:followers',
        'channel:moderate',
        'channel:read:subscriptions',
        'bits:read',
        'channel:read:redemptions'
    ]
    
    scope_string = quote(' '.join(scopes))
    redirect_uri_raw = _get_redirect_uri()
    redirect_uri = quote(redirect_uri_raw, safe='')
    
    oauth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope_string}"
    )
    
    print("🔗 OAuth URL Generated!")
    print("=" * 60)
    print(oauth_url)
    print("=" * 60)
    print()
    print(f"Redirect URI in use: {redirect_uri_raw}")
    print("⚠️ This MUST exactly match one OAuth Redirect URL configured in your Twitch app settings.")
    print("⚠️ This is unrelated to Twitch username capitalization (meangenebot vs MeanGeneBot).")
    print("   Twitch Dev Console: https://dev.twitch.tv/console/apps")
    print()
    print("📋 Instructions:")
    print("1. Set TWITCH_REDIRECT_URI in .env to a redirect URL allowed in your Twitch app")
    print("2. Open the URL above while logged into your MEANGENEBOT account")
    print("3. Authorize the application")
    print("4. Copy the 'code' parameter from the redirect URL")
    print("5. Exchange that code for access/refresh tokens")
    print()
    print("🌐 Opening URL in browser...")
    
    try:
        webbrowser.open(oauth_url)
    except Exception as e:
        print(f"Could not open browser: {e}")

def print_quick_fix():
    """Print quick fix options"""
    print("🚀 Quick Fix Options:")
    print()
    print("Option 1 - Use iamdar as bot (EASIEST):")
    print("   Change TWITCH_BOT_ID from 'meangenebot' to 'iamdar' in your .env file")
    print()
    print("Option 2 - Get new token for meangenebot:")
    print("   1. Run: python -m bot.oauth_helper")
    print("   2. Follow the OAuth flow while logged in as meangenebot")
    print("   3. Update TWITCH_OAUTH_TOKEN in your .env file")
    print()
    print("Option 3 - Use existing token but fix identity:")
    print("   Your current token might work if you change the bot ID to match")

if __name__ == "__main__":
    import sys
    
    print("🤖 Mean Gene Bot - OAuth Helper")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "url":
        generate_oauth_url()
    else:
        print_quick_fix()
        print()
        response = input("Generate OAuth URL? (y/n): ").lower()
        if response in ['y', 'yes']:
            generate_oauth_url()