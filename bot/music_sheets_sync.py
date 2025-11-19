"""
Enhanced Music Google Sheets Sync
Manages both catalog (all songs) and live queue sheets
Updates automatically on any queue change
"""
import json
import logging
import os
from typing import List, Dict, Optional
from bot.google_sheets_sync import write_full_sheet

LOG = logging.getLogger("music_sheets_sync")

def load_playlist_data() -> List[Dict]:
    """Load playlist data from cache file"""
    try:
        with open('data/playlist_cache.json', 'r', encoding='utf-8') as f:
            songs = json.load(f)
        return songs
    except Exception as e:
        LOG.error(f"Error loading playlist cache: {e}")
        return []

def format_catalog_for_sheets(songs: List[Dict]) -> List[Dict]:
    """Format complete song catalog for Google Sheets"""
    formatted_songs = []
    
    for song in songs:
        # Format duration as MM:SS
        minutes = song['duration'] // 60
        seconds = song['duration'] % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
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

def format_queue_for_sheets(queue_data: List[Dict]) -> List[Dict]:
    """Format current queue for Google Sheets
    
    Expected queue_data format:
    [
        {
            'position': 1,
            'title': 'Song Title',
            'artist': 'Artist Name', 
            'duration': '4:32',
            'requester': 'username',
            'catalog_number': 42,
            'request_type': 'playlist' or 'youtube',
            'youtube_url': 'https://...' (optional)
        }
    ]
    """
    if not queue_data:
        # Return empty queue message
        return [{
            'Position': 'Queue Empty',
            'Title': 'No songs currently queued',
            'Artist': 'Use !srx [number] to request songs',
            'Duration': '',
            'Requester': '',
            'Catalog #': '',
            'Request Type': '',
            'Command Used': 'Browse catalog below for available songs'
        }]
    
    formatted_queue = []
    for item in queue_data:
        row = {
            'Position': item.get('position', ''),
            'Title': item.get('title', ''),
            'Artist': item.get('artist', ''),
            'Duration': item.get('duration', ''),
            'Requester': item.get('requester', ''),
            'Catalog #': item.get('catalog_number', '') if item.get('request_type') == 'playlist' else 'YouTube',
            'Request Type': 'Playlist (FREE)' if item.get('request_type') == 'playlist' else 'YouTube (1 Quarter)',
            'Command Used': f"!srx {item.get('catalog_number', '')}" if item.get('request_type') == 'playlist' else '!sr [URL]'
        }
        formatted_queue.append(row)
    
    return formatted_queue

def sync_catalog_to_sheets(json_key_path: str, spreadsheet_id: str, sheet_name: str = "Catalog") -> bool:
    """Sync the complete song catalog to Google Sheets"""
    try:
        songs = load_playlist_data()
        if not songs:
            LOG.error("No songs found in playlist cache")
            return False
        
        formatted_songs = format_catalog_for_sheets(songs)
        write_full_sheet(json_key_path, spreadsheet_id, sheet_name, formatted_songs)
        
        LOG.info(f"Successfully synced {len(formatted_songs)} songs to catalog sheet")
        return True
        
    except Exception as e:
        LOG.error(f"Error syncing catalog to sheets: {e}")
        return False

def sync_queue_to_sheets(queue_data: List[Dict], json_key_path: str, spreadsheet_id: str, sheet_name: str = "Current Queue") -> bool:
    """Sync current queue to Google Sheets"""
    try:
        formatted_queue = format_queue_for_sheets(queue_data)
        write_full_sheet(json_key_path, spreadsheet_id, sheet_name, formatted_queue)
        
        queue_size = len(queue_data) if queue_data else 0
        LOG.info(f"Successfully synced queue ({queue_size} songs) to sheets")
        return True
        
    except Exception as e:
        LOG.error(f"Error syncing queue to sheets: {e}")
        return False

def sync_both_sheets(queue_data: List[Dict] = None) -> bool:
    """Sync both catalog and queue sheets"""
    json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
    
    if not json_key_path or not spreadsheet_id:
        LOG.warning("Google Sheets sync not configured")
        return False
    
    if not os.path.exists(json_key_path):
        LOG.warning(f"Service account key file not found: {json_key_path}")
        return False
    
    success = True
    
    # Sync catalog (all songs)
    if not sync_catalog_to_sheets(json_key_path, spreadsheet_id, "Catalog"):
        success = False
    
    # Sync queue (current queue)  
    if queue_data is not None:
        if not sync_queue_to_sheets(queue_data, json_key_path, spreadsheet_id, "Current Queue"):
            success = False
    
    return success

def get_music_system_summary() -> Dict:
    """Get summary statistics for both catalog and queue"""
    songs = load_playlist_data()
    if not songs:
        return {}
    
    # Calculate catalog statistics
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
        'catalog': {
            'total_songs': total_songs,
            'total_duration': f"{total_hours}h {total_minutes}m",
            'played_songs': played_songs,
            'unique_artists': len(artists),
            'top_artists': top_artists
        }
    }

def format_commands_for_sheets() -> List[Dict]:
    """Format all bot commands for Google Sheets reference"""
    commands = [
        # Music Commands
        {
            'Category': 'Music - Requests',
            'Command': '!srx [number]',
            'Description': 'Request a song from the playlist by catalog number',
            'Example': '!srx 42',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Music - Requests',
            'Command': '!sr [YouTube URL]',
            'Description': 'Request a YouTube song (not in catalog)',
            'Example': '!sr https://youtube.com/watch?v=...',
            'Permission': 'Everyone',
            'Cost': '1 Quarter'
        },
        {
            'Category': 'Music - Queue',
            'Command': '!queue',
            'Description': 'Show current song queue',
            'Example': '!queue',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Music - Queue',
            'Command': '!clearqueue',
            'Description': 'Clear the entire song queue',
            'Example': '!clearqueue',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        {
            'Category': 'Music - Info',
            'Command': '!plstats',
            'Description': 'Show playlist statistics and queue info',
            'Example': '!plstats',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Music - Admin',
            'Command': '!syncplaylist',
            'Description': 'Force sync both catalog and queue to Google Sheets',
            'Example': '!syncplaylist',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        {
            'Category': 'Music - Admin',
            'Command': '!synccatalog',
            'Description': 'Force sync catalog only to Google Sheets',
            'Example': '!synccatalog',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        
        # Game Commands
        {
            'Category': 'Games',
            'Command': '!d20',
            'Description': 'Roll a 20-sided die',
            'Example': '!d20',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Games',
            'Command': '!tic',
            'Description': 'Play tic-tac-toe',
            'Example': '!tic',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        
        # Raffle Commands
        {
            'Category': 'Raffle',
            'Command': '!raffle',
            'Description': 'Join the current raffle (if active)',
            'Example': '!raffle',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Raffle',
            'Command': '!startraffle',
            'Description': 'Start a new raffle',
            'Example': '!startraffle Cool Prize',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        {
            'Category': 'Raffle',
            'Command': '!endraffle',
            'Description': 'End current raffle and pick winner',
            'Example': '!endraffle',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        
        # Social Commands
        {
            'Category': 'Social',
            'Command': '!shoutout [username]',
            'Description': 'Give a shoutout to another streamer',
            'Example': '!shoutout coolstreamer',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        {
            'Category': 'Social',
            'Command': '!quote',
            'Description': 'Get a random quote',
            'Example': '!quote',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        
        # Fun Commands
        {
            'Category': 'Fun',
            'Command': '!dah',
            'Description': 'Dah!',
            'Example': '!dah',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        {
            'Category': 'Fun',
            'Command': '!derpism',
            'Description': 'Get a random derpism',
            'Example': '!derpism',
            'Permission': 'Everyone',
            'Cost': 'FREE'
        },
        
        # Mod Commands
        {
            'Category': 'Moderation',
            'Command': '!modnews',
            'Description': 'Post mod news/announcements',
            'Example': '!modnews Stream starting soon!',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        },
        
        # Overlay Commands
        {
            'Category': 'Overlay',
            'Command': '!overlay [type]',
            'Description': 'Trigger overlay effects',
            'Example': '!overlay anime',
            'Permission': 'Mods Only',
            'Cost': 'FREE'
        }
    ]
    
    return commands

def sync_commands_to_sheets(json_key_path: str, spreadsheet_id: str, sheet_name: str = "Commands") -> bool:
    """Sync bot commands reference to Google Sheets"""
    try:
        commands = format_commands_for_sheets()
        write_full_sheet(json_key_path, spreadsheet_id, sheet_name, commands)
        
        LOG.info(f"Successfully synced {len(commands)} commands to reference sheet")
        return True
        
    except Exception as e:
        LOG.error(f"Error syncing commands to sheets: {e}")
        return False

def sync_all_sheets(queue_data: List[Dict] = None) -> bool:
    """Sync catalog, queue, AND commands sheets"""
    json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
    
    if not json_key_path or not spreadsheet_id:
        LOG.warning("Google Sheets sync not configured")
        return False
    
    if not os.path.exists(json_key_path):
        LOG.warning(f"Service account key file not found: {json_key_path}")
        return False
    
    success = True
    
    # Sync catalog (all songs)
    if not sync_catalog_to_sheets(json_key_path, spreadsheet_id, "Catalog"):
        success = False
    
    # Sync queue (current queue)  
    if queue_data is not None:
        if not sync_queue_to_sheets(queue_data, json_key_path, spreadsheet_id, "Current Queue"):
            success = False
    
    # Sync commands reference
    if not sync_commands_to_sheets(json_key_path, spreadsheet_id, "Commands"):
        success = False
    
    return success

class MusicSheetsManager:
    """Manager class for music sheets sync with queue tracking"""
    
    def __init__(self):
        self.current_queue = []
        self.is_configured = self._check_configuration()
    
    def _check_configuration(self) -> bool:
        """Check if Google Sheets sync is properly configured"""
        json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
        
        if not json_key_path or not spreadsheet_id:
            return False
        
        return os.path.exists(json_key_path)
    
    def update_queue(self, queue_data: List[Dict]):
        """Update queue and sync to sheets automatically"""
        self.current_queue = queue_data
        
        if self.is_configured:
            try:
                sync_both_sheets(queue_data)
                LOG.info(f"Auto-synced queue update ({len(queue_data)} songs)")
            except Exception as e:
                LOG.error(f"Failed to auto-sync queue: {e}")
    
    def force_sync_catalog(self) -> bool:
        """Force sync catalog only"""
        if not self.is_configured:
            return False
        
        json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
        
        return sync_catalog_to_sheets(json_key_path, spreadsheet_id, "Catalog")
    
    def force_sync_all(self) -> bool:
        """Force sync catalog, queue, and commands"""
        if not self.is_configured:
            return False
        
        return sync_all_sheets(self.current_queue)
    
    def force_sync_commands(self) -> bool:
        """Force sync commands reference sheet only"""
        if not self.is_configured:
            return False
        
        json_key_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
        
        return sync_commands_to_sheets(json_key_path, spreadsheet_id, "Commands")

# Global instance for use across the bot
music_sheets_manager = MusicSheetsManager()