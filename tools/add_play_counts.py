#!/usr/bin/env python3
"""
Add play_count field to all songs in playlist_cache.json
"""

import json
import os

# Get the project root directory  
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYLIST_FILE = os.path.join(PROJECT_ROOT, "data", "playlist_cache.json")

def add_play_counts():
    """Add play_count field to all songs"""
    
    # Load current playlist
    with open(PLAYLIST_FILE, 'r') as f:
        playlist = json.load(f)
    
    print(f"Found {len(playlist)} songs in playlist")
    
    # Add play_count field to each song (default to 0)
    updated_count = 0
    for song in playlist:
        if 'play_count' not in song:
            song['play_count'] = 0
            updated_count += 1
    
    # Save updated playlist
    with open(PLAYLIST_FILE, 'w') as f:
        json.dump(playlist, f, indent=2)
    
    print(f"Added play_count to {updated_count} songs")
    print("Updated playlist_cache.json")

if __name__ == "__main__":
    add_play_counts()