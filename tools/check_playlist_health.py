#!/usr/bin/env python3
"""
Check all playlist songs for broken YouTube URLs
"""

import json
import os
import asyncio

# Optional yt-dlp import
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("❌ yt-dlp not available - install with: pip install yt-dlp")
    exit(1)

# Get the project root directory  
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, "data", "playlist_cache.json")

async def check_youtube_url(url, title, artist, number):
    """Check if a YouTube URL is working"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        if info:
            return True, f"✅ #{number}: {title} by {artist} - WORKING"
        else:
            return False, f"⚠️ #{number}: {title} by {artist} - No info extracted"
            
    except Exception as e:
        error_type = "Unknown"
        if "Video unavailable" in str(e):
            error_type = "Video unavailable"
        elif "Private video" in str(e):
            error_type = "Private video"
        elif "removed" in str(e).lower():
            error_type = "Video removed"
        elif "deleted" in str(e).lower():
            error_type = "Video deleted"
        
        return False, f"❌ #{number}: {title} by {artist} - {error_type}"

async def check_all_playlist_songs():
    """Check all songs in playlist for broken URLs"""
    
    if not YT_DLP_AVAILABLE:
        print("❌ Cannot check songs without yt-dlp")
        return
    
    # Load playlist
    with open(PLAYLIST_FILE, 'r') as f:
        playlist = json.load(f)
    
    print(f"🔍 Checking {len(playlist)} songs for broken URLs...\n")
    
    working_songs = []
    broken_songs = []
    
    # Check each song
    for i, song in enumerate(playlist, 1):
        number = song.get('number', i)
        title = song.get('title', 'Unknown')
        artist = song.get('artist', 'Unknown')
        url = song.get('youtube_url', '')
        
        if not url:
            broken_songs.append(f"❌ #{number}: {title} by {artist} - No URL")
            continue
        
        print(f"Checking {i}/{len(playlist)}: {title} by {artist}...", end=" ")
        
        is_working, result = await check_youtube_url(url, title, artist, number)
        
        if is_working:
            working_songs.append(result)
            print("✅")
        else:
            broken_songs.append(result)
            print("❌")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Print summary
    print(f"\n📊 PLAYLIST CHECK COMPLETE:")
    print(f"✅ Working songs: {len(working_songs)}")
    print(f"❌ Broken songs: {len(broken_songs)}")
    print(f"📈 Success rate: {len(working_songs)/(len(working_songs)+len(broken_songs))*100:.1f}%")
    
    if broken_songs:
        print(f"\n🚨 BROKEN SONGS FOUND:")
        for broken in broken_songs:
            print(broken)
        
        print(f"\n💡 To fix broken songs, use: !music fix [number]")
    else:
        print(f"\n🎉 All songs are working!")

if __name__ == "__main__":
    asyncio.run(check_all_playlist_songs())