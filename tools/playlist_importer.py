#!/usr/bin/env python3
"""
Playlist Importer Tool for Mean Gene Bot
Imports songs from various sources into the bot's playlist cache
"""

import json
import os
import sys
import yt_dlp
from typing import List, Dict

# Add bot directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class PlaylistImporter:
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.playlist_file = os.path.join(self.project_root, "data", "playlist_cache.json")
        
    def load_existing_playlist(self) -> List[Dict]:
        """Load existing playlist cache"""
        try:
            if os.path.exists(self.playlist_file):
                with open(self.playlist_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading existing playlist: {e}")
        return []
    
    def save_playlist(self, playlist: List[Dict]):
        """Save playlist to cache file"""
        try:
            os.makedirs(os.path.dirname(self.playlist_file), exist_ok=True)
            with open(self.playlist_file, 'w') as f:
                json.dump(playlist, f, indent=2)
            print(f"✅ Playlist saved to {self.playlist_file}")
        except Exception as e:
            print(f"❌ Error saving playlist: {e}")
    
    def extract_youtube_playlist(self, playlist_url: str) -> List[Dict]:
        """Extract songs from YouTube playlist"""
        print(f"🔍 Extracting from YouTube playlist: {playlist_url}")
        
        ydl_opts = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        songs = []
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(playlist_url, download=False)
                
                if 'entries' not in playlist_info:
                    print("❌ No songs found in playlist")
                    return []
                
                print(f"📋 Found {len(playlist_info['entries'])} songs")
                
                for i, entry in enumerate(playlist_info['entries'], 1):
                    if entry is None:
                        continue
                        
                    # Extract detailed info for each song
                    try:
                        song_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        detailed_info = ydl.extract_info(song_url, download=False)
                        
                        song = {
                            "number": i,
                            "title": detailed_info.get('title', entry.get('title', 'Unknown Title')),
                            "artist": detailed_info.get('uploader', 'Unknown Artist'),
                            "youtube_url": song_url,
                            "duration": detailed_info.get('duration', 300),
                            "verified": True
                        }
                        
                        songs.append(song)
                        print(f"  {i:2d}. {song['title']} - {song['artist']} ({song['duration']}s)")
                        
                    except Exception as e:
                        print(f"  ❌ Failed to extract: {entry.get('title', 'Unknown')} - {e}")
                        continue
                        
        except Exception as e:
            print(f"❌ Error extracting playlist: {e}")
            
        return songs
    
    def import_from_binary_playlist(self, file_path: str) -> List[Dict]:
        """Try to import from binary playlist file"""
        print(f"📁 Attempting to decode binary playlist: {file_path}")
        
        # Run the binary decoder
        import subprocess
        try:
            result = subprocess.run([
                "python", 
                os.path.join(os.path.dirname(__file__), "binary_playlist_decoder.py"),
                file_path
            ], capture_output=True, text=True)
            
            print("🔍 Binary playlist analysis:")
            print(result.stdout)
            
            print("\n⚠️ This appears to be a proprietary binary playlist format.")
            print("💡 Suggested alternatives:")
            print("   1. Export playlist as .m3u or .pls from the original software")
            print("   2. Copy song names manually to a text file")
            print("   3. Recreate playlist using YouTube links")
            
            return []
            
        except Exception as e:
            print(f"❌ Error analyzing binary playlist: {e}")
            return []

    def import_from_text_file(self, file_path: str) -> List[Dict]:
        """Import from text file with various formats"""
        print(f"📄 Reading from text file: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return []
        
        # Check if it's a binary file
        try:
            with open(file_path, 'rb') as f:
                first_bytes = f.read(100)
                # Check if it contains mostly non-printable characters
                non_printable = sum(1 for b in first_bytes if b < 32 or b > 126)
                if non_printable > len(first_bytes) * 0.3:  # More than 30% non-printable
                    print("🔍 Detected binary file format")
                    return self.import_from_binary_playlist(file_path)
        except Exception:
            pass
        
        songs = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            print(f"📋 Found {len(lines)} lines to process")
            
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                song = None
                
                # Try different formats
                if 'youtube.com' in line or 'youtu.be' in line:
                    # YouTube URL format
                    song = self.extract_youtube_song(line, i)
                elif ' - ' in line:
                    # "Artist - Song Title" format
                    parts = line.split(' - ', 1)
                    if len(parts) == 2:
                        song = {
                            "number": i,
                            "title": parts[1].strip(),
                            "artist": parts[0].strip(),
                            "youtube_url": "",  # To be filled manually
                            "duration": 300,
                            "verified": False
                        }
                else:
                    # Just song title
                    song = {
                        "number": i,
                        "title": line.strip(),
                        "artist": "Unknown Artist",
                        "youtube_url": "",
                        "duration": 300,
                        "verified": False
                    }
                
                if song:
                    songs.append(song)
                    print(f"  {i:2d}. {song['title']} - {song['artist']}")
                    
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            
        return songs
    
    def extract_youtube_song(self, url: str, number: int) -> Dict:
        """Extract single YouTube song info"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                return {
                    "number": number,
                    "title": info.get('title', 'Unknown Title'),
                    "artist": info.get('uploader', 'Unknown Artist'),
                    "youtube_url": url,
                    "duration": info.get('duration', 300),
                    "verified": True
                }
                
        except Exception as e:
            print(f"❌ Error extracting {url}: {e}")
            return None
    
    def merge_playlists(self, existing: List[Dict], new_songs: List[Dict], start_number: int = None) -> List[Dict]:
        """Merge new songs with existing playlist"""
        if start_number is None:
            start_number = len(existing) + 1
        
        # Renumber new songs
        for i, song in enumerate(new_songs):
            song['number'] = start_number + i
        
        return existing + new_songs

def main():
    importer = PlaylistImporter()
    
    print("🎵 Mean Gene Bot Playlist Importer")
    print("=" * 50)
    
    existing_playlist = importer.load_existing_playlist()
    print(f"📋 Current playlist has {len(existing_playlist)} songs")
    
    while True:
        print("\nChoose import method:")
        print("1. YouTube Playlist URL")
        print("2. Text File (Artist - Title format)")
        print("3. Text File (YouTube URLs)")
        print("4. Binary Playlist File (.playlist, .wpl, etc.)")
        print("5. Show current playlist")
        print("6. Save and exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == "1":
            url = input("Enter YouTube playlist URL: ").strip()
            if url:
                new_songs = importer.extract_youtube_playlist(url)
                if new_songs:
                    start_num = len(existing_playlist) + 1
                    existing_playlist = importer.merge_playlists(existing_playlist, new_songs, start_num)
                    print(f"✅ Added {len(new_songs)} songs to playlist")
                    
        elif choice == "2" or choice == "3":
            file_path = input("Enter path to text file: ").strip()
            if file_path:
                new_songs = importer.import_from_text_file(file_path)
                if new_songs:
                    start_num = len(existing_playlist) + 1
                    existing_playlist = importer.merge_playlists(existing_playlist, new_songs, start_num)
                    print(f"✅ Added {len(new_songs)} songs to playlist")
                    
        elif choice == "4":
            file_path = input("Enter path to binary playlist file: ").strip()
            if file_path:
                new_songs = importer.import_from_binary_playlist(file_path)
                if new_songs:
                    start_num = len(existing_playlist) + 1
                    existing_playlist = importer.merge_playlists(existing_playlist, new_songs, start_num)
                    print(f"✅ Added {len(new_songs)} songs to playlist")
                    
        elif choice == "5":
            print(f"\n📋 Current Playlist ({len(existing_playlist)} songs):")
            for song in existing_playlist:
                print(f"  {song['number']:2d}. {song['title']} - {song['artist']} ({song['duration']}s)")
                
        elif choice == "6":
            if existing_playlist:
                importer.save_playlist(existing_playlist)
                print(f"✅ Saved playlist with {len(existing_playlist)} songs")
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main()