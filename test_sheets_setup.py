"""
Test script for Google Sheets playlist sync
Run this to verify your setup is working
"""
import os
import sys
from pathlib import Path

def test_google_sheets_setup():
    print("=== Google Sheets Playlist Sync Test ===\n")
    
    # Check environment variables
    json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
    
    print("1. Checking environment variables...")
    if not json_key_path:
        print("   ❌ GOOGLE_SERVICE_ACCOUNT_JSON not set")
        print("   Set this to your service account JSON file path")
        return False
    else:
        print(f"   ✅ GOOGLE_SERVICE_ACCOUNT_JSON: {json_key_path}")
    
    if not spreadsheet_id:
        print("   ❌ PLAYLIST_SPREADSHEET_ID not set") 
        print("   Set this to your Google Sheet ID")
        return False
    else:
        print(f"   ✅ PLAYLIST_SPREADSHEET_ID: {spreadsheet_id}")
    
    # Check if JSON key file exists
    print("\n2. Checking service account key file...")
    if not os.path.exists(json_key_path):
        print(f"   ❌ Service account JSON file not found: {json_key_path}")
        return False
    else:
        print(f"   ✅ Service account JSON file exists")
    
    # Check if playlist cache exists
    print("\n3. Checking playlist data...")
    playlist_path = "data/playlist_cache.json"
    if not os.path.exists(playlist_path):
        print(f"   ❌ Playlist cache not found: {playlist_path}")
        return False
    else:
        print(f"   ✅ Playlist cache exists")
    
    # Test imports
    print("\n4. Testing imports...")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        print("   ✅ Google Sheets libraries imported successfully")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    # Test playlist sync module
    print("\n5. Testing playlist sync module...")
    try:
        sys.path.insert(0, os.getcwd())
        from bot.playlist_sheets_sync import load_playlist_data, get_playlist_summary
        
        songs = load_playlist_data()
        stats = get_playlist_summary()
        
        print(f"   ✅ Loaded {len(songs)} songs")
        print(f"   ✅ Statistics: {stats['total_songs']} songs, {stats['total_duration']}")
    except Exception as e:
        print(f"   ❌ Playlist sync module error: {e}")
        return False
    
    # Test Google Sheets connection (optional)
    print("\n6. Testing Google Sheets connection...")
    try:
        creds = Credentials.from_service_account_file(json_key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(spreadsheet_id)
        print(f"   ✅ Successfully connected to Google Sheet: '{sheet.title}'")
    except Exception as e:
        print(f"   ❌ Google Sheets connection error: {e}")
        print("   Make sure the service account has access to the sheet")
        return False
    
    print(f"\n🎉 ALL TESTS PASSED! 🎉")
    print(f"\nYou can now use these commands in your bot:")
    print(f"   • !syncplaylist - Sync playlist to Google Sheets")
    print(f"   • !plstats - Show playlist statistics")
    
    return True

if __name__ == "__main__":
    success = test_google_sheets_setup()
    if not success:
        print(f"\n❌ Setup incomplete. Please fix the issues above.")
        sys.exit(1)