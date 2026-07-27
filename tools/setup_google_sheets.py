"""
Google Sheets Setup Helper
This script helps you set up the Google Sheets integration step by step
"""

import os
import json

def main():
    print("=== Google Sheets Setup Helper ===\n")
    
    print("This will help you set up Google Sheets integration for your playlist.\n")
    
    # Step 1: Check current status
    print("1. Checking current setup...")
    
    env_file_exists = os.path.exists('.env')
    template_exists = os.path.exists('.env.template')
    
    if env_file_exists:
        print("   ✓ .env file exists")
    elif template_exists:
        print("   ! .env file missing, but .env.template exists")
        print("   → You need to copy .env.template to .env and fill in your values")
    else:
        print("   X No .env file found")
    
    # Step 2: Guide user through Google Cloud setup
    print("\n2. Google Cloud Service Account Setup:")
    print("   a) Go to: https://console.cloud.google.com/")
    print("   b) Create/select a project")
    print("   c) Enable Google Sheets API (APIs & Services → Library)")
    print("   d) Create service account (APIs & Services → Credentials)")
    print("   e) Download JSON key to: C:\\keys\\mean-gene-bot-service-account.json")
    
    # Step 3: Google Sheet setup
    print("\n3. Google Sheet Setup:")
    print("   a) Go to: https://sheets.google.com/")
    print("   b) Create a new blank sheet")
    print("   c) Share it with your service account email (Editor permissions)")
    print("   d) Copy the sheet ID from the URL")
    
    # Step 4: Environment variables
    print("\n4. Set Environment Variables:")
    print("   Add these to your .env file:")
    print("   GOOGLE_SERVICE_ACCOUNT_JSON=C:\\keys\\mean-gene-bot-service-account.json")
    print("   PLAYLIST_SPREADSHEET_ID=your_sheet_id_here")
    
    # Step 5: Test
    print("\n5. Test the Setup:")
    print("   a) Restart your bot")
    print("   b) Use !syncplaylist in chat (moderator only)")
    print("   c) Check your Google Sheet for the playlist data")
    
    print("\n=== Quick Verification ===")
    
    # Check if key file exists
    key_path = "C:\\keys\\mean-gene-bot-service-account.json"
    if os.path.exists(key_path):
        print("✓ Service account JSON file found")
    else:
        print("X Service account JSON file not found")
        print(f"  Create folder: C:\\keys\\")
        print(f"  Download JSON to: {key_path}")
    
    # Check environment variables
    json_key = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    sheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
    
    if json_key:
        print(f"✓ GOOGLE_SERVICE_ACCOUNT_JSON set: {json_key}")
    else:
        print("X GOOGLE_SERVICE_ACCOUNT_JSON not set")
    
    if sheet_id:
        print(f"✓ PLAYLIST_SPREADSHEET_ID set: {sheet_id}")
    else:
        print("X PLAYLIST_SPREADSHEET_ID not set")
    
    # Final status
    all_ready = (
        os.path.exists(key_path) and 
        json_key and 
        sheet_id and 
        json_key == key_path
    )
    
    if all_ready:
        print("\n🎉 Setup appears complete! Try !syncplaylist in your bot chat.")
    else:
        print("\n⚠️  Setup incomplete. Follow the steps above.")
        print("    After completing setup, restart your bot and try !syncplaylist")

if __name__ == "__main__":
    main()