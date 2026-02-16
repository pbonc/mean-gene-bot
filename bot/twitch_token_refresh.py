#!/usr/bin/env python3
"""
Twitch Token Refresh Utility for Mean Gene Bot

This utility helps automatically refresh Twitch OAuth tokens and handles
client credential regeneration when needed.
"""

import os
import json
import aiohttp
import asyncio
from datetime import datetime
from dotenv import load_dotenv, set_key, find_dotenv

# Load environment variables
load_dotenv()

class TwitchTokenManager:
    def __init__(self):
        self.client_id = os.getenv('TWITCH_CLIENT_ID')
        self.client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        self.refresh_token = os.getenv('TWITCH_REFRESH_TOKEN')
        self.oauth_token = os.getenv('TWITCH_OAUTH_TOKEN')
        self.env_file = find_dotenv()
        
    async def refresh_oauth_token(self):
        """Refresh the OAuth token using the refresh token"""
        if not self.refresh_token:
            print("❌ No refresh token available. Manual re-authorization required.")
            return False
            
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        
                        # Update tokens in .env file
                        set_key(self.env_file, 'TWITCH_OAUTH_TOKEN', token_data['access_token'])
                        if 'refresh_token' in token_data:
                            set_key(self.env_file, 'TWITCH_REFRESH_TOKEN', token_data['refresh_token'])
                            
                        print("✅ OAuth token refreshed successfully!")
                        print(f"   New token: {token_data['access_token'][:20]}...")
                        return True
                    else:
                        error_data = await response.json()
                        print(f"❌ Failed to refresh token: {error_data}")
                        return False
            except Exception as e:
                print(f"❌ Error refreshing token: {e}")
                return False
    
    async def validate_token(self, token=None):
        """Validate a Twitch OAuth token"""
        token = token or self.oauth_token
        if not token:
            return False, "No token provided"
            
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {'Authorization': f'OAuth {token}'}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return True, data
                    else:
                        return False, await response.text()
            except Exception as e:
                return False, str(e)
    
    async def get_client_credentials_token(self):
        """Get a new client credentials token"""
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        print("✅ Client credentials token obtained successfully!")
                        return True, token_data['access_token']
                    else:
                        error_data = await response.json()
                        print(f"❌ Failed to get client credentials: {error_data}")
                        return False, None
            except Exception as e:
                print(f"❌ Error getting client credentials: {e}")
                return False, None
    
    def print_current_config(self):
        """Print current configuration for debugging"""
        print("🔍 Current Twitch Configuration:")
        print(f"   Client ID: {self.client_id[:20] if self.client_id else 'NOT SET'}...")
        print(f"   Client Secret: {'SET' if self.client_secret else 'NOT SET'}")
        print(f"   OAuth Token: {self.oauth_token[:20] if self.oauth_token else 'NOT SET'}...")
        print(f"   Refresh Token: {'SET' if self.refresh_token else 'NOT SET'}")
        print(f"   Bot ID: {os.getenv('TWITCH_BOT_ID', 'NOT SET')}")
        print(f"   Channels: {os.getenv('TWITCH_CHANNELS', 'NOT SET')}")
    
    async def diagnose_and_fix(self):
        """Diagnose token issues and attempt to fix them"""
        print("🔧 Diagnosing Twitch authentication...")
        self.print_current_config()
        
        if not self.client_id or not self.client_secret:
            print("❌ Missing client ID or secret. Please check your Twitch app settings.")
            return False
        
        # Test client credentials
        print("\n📡 Testing client credentials...")
        success, token = await self.get_client_credentials_token()
        if not success:
            print("❌ Client credentials failed. Your client secret may be invalid.")
            print("   Please regenerate your client secret in Twitch Dev Console:")
            print("   https://dev.twitch.tv/console/apps")
            return False
        
        # Test OAuth token if available
        if self.oauth_token:
            print("\n🔐 Validating OAuth token...")
            valid, result = await self.validate_token()
            if valid:
                print("✅ OAuth token is valid!")
                print(f"   Login: {result.get('login', 'Unknown')}")
                print(f"   User ID: {result.get('user_id', 'Unknown')}")
                
                # Check if the token login matches the bot ID
                token_login = result.get('login', '').lower()
                expected_bot = os.getenv('TWITCH_BOT_ID', '').lower()
                if token_login != expected_bot:
                    print(f"⚠️  Token login '{token_login}' doesn't match bot ID '{expected_bot}'")
                    print("   You may be logging in as the wrong user!")
                
            else:
                print(f"❌ OAuth token invalid: {result}")
                print("🔄 Attempting to refresh token...")
                if await self.refresh_oauth_token():
                    return await self.diagnose_and_fix()
                else:
                    print("❌ Could not refresh token. Manual re-authorization required.")
                    return False
        
        print("\n✅ Authentication setup appears to be working!")
        return True

async def main():
    """Main function to run token diagnostics and refresh"""
    print("🤖 Mean Gene Bot - Twitch Token Manager")
    print("=" * 50)
    
    manager = TwitchTokenManager()
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "refresh":
            print("🔄 Refreshing OAuth token...")
            await manager.refresh_oauth_token()
        elif command == "validate":
            print("🔍 Validating current token...")
            valid, result = await manager.validate_token()
            if valid:
                print("✅ Token is valid!")
                print(f"   Login: {result.get('login')}")
                print(f"   User ID: {result.get('user_id')}")
            else:
                print(f"❌ Token invalid: {result}")
        elif command == "diagnose":
            await manager.diagnose_and_fix()
        else:
            print("❌ Unknown command. Use: refresh, validate, or diagnose")
    else:
        # Default: run full diagnosis
        await manager.diagnose_and_fix()

if __name__ == "__main__":
    asyncio.run(main())