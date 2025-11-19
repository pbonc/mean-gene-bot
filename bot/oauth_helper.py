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
        'channel:moderate',
        'channel:read:subscriptions',
        'bits:read',
        'channel:read:redemptions'
    ]
    
    scope_string = quote(' '.join(scopes))
    redirect_uri = quote('http://localhost:3000')  # You'll need to add this to your Twitch app
    
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
    print("📋 Instructions:")
    print("1. Copy the URL above")
    print("2. Open it in a browser while logged into your MEANGENEBOT account")
    print("3. Authorize the application")
    print("4. Copy the 'code' parameter from the redirect URL")
    print("5. Use that code to get your OAuth token")
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