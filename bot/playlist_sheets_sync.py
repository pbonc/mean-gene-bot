"""
Playlist Google Sheets Sync Module
Syncs the song playlist to Google Sheets for viewer reference
"""
import json
import logging
from typing import List, Dict
from bot.google_sheets_sync import write_full_sheet

LOG = logging.getLogger("playlist_sheets_sync")

def load_playlist_data() -> List[Dict]:
    """Load playlist data from cache file"""
    try:
        with open('data/playlist_cache.json', 'r', encoding='utf-8') as f:
            songs = json.load(f)
        
        LOG.info(f"Loaded {len(songs)} songs from playlist cache")
        return songs
    except Exception as e:
        LOG.error(f"Error loading playlist cache: {e}")
        return []

def format_playlist_for_sheets(songs: List[Dict]) -> List[Dict]:
    """Format song data for Google Sheets export"""
    formatted_songs = []
    
    for song in songs:
        # Format duration as MM:SS
        minutes = song['duration'] // 60
        seconds = song['duration'] % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Create sheet row
        row = {
            'Number': song['number'],
            'Title': song['title'],
            'Artist': song['artist'],
            'Duration': duration_str,
            'Play Count': song.get('play_count', 0),
            'YouTube URL': song.get('youtube_url', ''),
            'Request Command': f"!srx {song['number']}"
        }
        formatted_songs.append(row)
    
    return formatted_songs

def sync_playlist_to_sheets(json_key_path: str, spreadsheet_id: str, sheet_name: str = "playlist") -> bool:
    """Sync the complete playlist to Google Sheets"""
    try:
        # Load and format playlist data
        songs = load_playlist_data()
        if not songs:
            LOG.error("No songs found in playlist cache")
            return False
        
        formatted_songs = format_playlist_for_sheets(songs)
        
        # Write to Google Sheets
        write_full_sheet(json_key_path, spreadsheet_id, sheet_name, formatted_songs)
        
        LOG.info(f"Successfully synced {len(formatted_songs)} songs to Google Sheets")
        return True
        
    except Exception as e:
        LOG.error(f"Error syncing playlist to sheets: {e}")
        return False

def get_playlist_summary() -> Dict:
    """Get summary statistics of the playlist"""
    songs = load_playlist_data()
    if not songs:
        return {}
    
    # Calculate statistics
    total_songs = len(songs)
    total_duration = sum(song['duration'] for song in songs)
    total_hours = total_duration // 3600
    total_minutes = (total_duration % 3600) // 60
    
    # Count by artist
    artists = {}
    played_songs = 0
    for song in songs:
        artist = song['artist']
        artists[artist] = artists.get(artist, 0) + 1
        if song.get('play_count', 0) > 0:
            played_songs += 1
    
    top_artists = sorted(artists.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'total_songs': total_songs,
        'total_duration': f"{total_hours}h {total_minutes}m",
        'played_songs': played_songs,
        'unique_artists': len(artists),
        'top_artists': top_artists
    }