import os
from twitchio.ext import commands
from bot.playlist_sheets_sync import sync_playlist_to_sheets, get_playlist_summary

# Path to the current song file (update this if your path changes)
SONG_FILE = r"C:\Users\darji\AppData\Roaming\Streamlabs\Streamlabs Chatbot\Services\Twitch\Files\currentsong.txt"

class SongCog(commands.Cog):
    """
    Cog for displaying the currently playing song using !song.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = SONG_FILE

    @commands.command(name="song", aliases=["currentsong"])
    async def song_cmd(self, ctx: commands.Context):
        """
        Display the currently playing song.
        Usage: !song
        """
        if not os.path.isfile(self.file_path):
            await ctx.send("Song: Song file not found.")
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                song = f.read().strip()
        except Exception as e:
            await ctx.send("Song: Error reading song file.")
            return

        if song:
            await ctx.send(f"Song: {song}")
        else:
            await ctx.send("Song: No song currently playing.")

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def now_playing(self, ctx: commands.Context):
        """
        Display the current song with catalog number if available.
        Does not show quarter-based (YouTube-only) songs.
        """
        try:
            from bot.commands.song_request_simple import song_manager
            
            # Check if music is currently playing
            if not song_manager.is_playing or not song_manager.current_song_info:
                await ctx.send("🎵 No song currently playing.")
                return
            
            song_info, username = song_manager.current_song_info
            
            # Skip quarter-based songs (YouTube-only requests)
            if username != "AutoPlaylist" and username != "System" and not song_info.get('number'):
                await ctx.send("🎵 A custom song is currently playing.")
                return
            
            title = song_info.get('title', 'Unknown')
            artist = song_info.get('artist', 'Unknown Artist')
            song_number = song_info.get('number')
            
            # Format the message
            if song_number:
                # Playlist song with catalog number
                duration_info = ""
                if song_info.get('duration'):
                    mins = song_info['duration'] // 60
                    secs = song_info['duration'] % 60
                    duration_info = f" ({mins}:{secs:02d})"
                
                message = f"🎵 **Now Playing:** #{song_number}: {title} - {artist}{duration_info}"
                
                # Add play count if available
                if song_info.get('play_count', 0) > 0:
                    message += f" [Played {song_info['play_count']} time(s)]"
            else:
                # Non-catalog song (shouldn't happen with current logic, but just in case)
                message = f"🎵 **Now Playing:** {title} - {artist}"
            
            await ctx.send(message)
            
        except Exception as e:
            await ctx.send(f"Error getting current song info: {str(e)}")

    @commands.command(name="syncplaylist", aliases=["syncpl"])
    async def sync_playlist_cmd(self, ctx: commands.Context):
        """
        Sync the song playlist catalog to Google Sheets (Moderator only).
        Usage: !syncplaylist
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can sync the playlist to Google Sheets.")
            return

        try:
            # Import the new music sheets manager
            from bot.music_sheets_sync import music_sheets_manager
            
            if not music_sheets_manager.is_configured:
                await ctx.send("❌ Music sheets sync not configured. Check GOOGLE_SERVICE_ACCOUNT_JSON and PLAYLIST_SPREADSHEET_ID.")
                return
            
            # Force sync both catalog and current queue
            success = music_sheets_manager.force_sync_all()
            
            if success:
                await ctx.send("✅ Music catalog and queue synced to Google Sheets!")
            else:
                await ctx.send("❌ Error syncing music sheets. Check logs.")
                
        except Exception as e:
            await ctx.send(f"❌ Error syncing music sheets: {str(e)}")

    @commands.command(name="synccatalog", aliases=["synccat"])
    async def sync_catalog_cmd(self, ctx: commands.Context):
        """
        Sync only the song catalog to Google Sheets (Moderator only).
        Usage: !synccatalog
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can sync the catalog.")
            return

        try:
            from bot.music_sheets_sync import music_sheets_manager
            
            if not music_sheets_manager.is_configured:
                await ctx.send("❌ Music sheets sync not configured.")
                return
            
            success = music_sheets_manager.force_sync_catalog()
            
            if success:
                await ctx.send("✅ Song catalog synced to Google Sheets!")
            else:
                await ctx.send("❌ Error syncing catalog.")
                
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    @commands.command(name="synccommands", aliases=["synccmd"])
    async def sync_commands_cmd(self, ctx: commands.Context):
        """
        Sync bot commands reference to Google Sheets (Moderator only).
        Usage: !synccommands
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can sync commands reference.")
            return

        try:
            from bot.music_sheets_sync import music_sheets_manager
            
            if not music_sheets_manager.is_configured:
                await ctx.send("❌ Music sheets sync not configured.")
                return
            
            success = music_sheets_manager.force_sync_commands()
            
            if success:
                await ctx.send("✅ Bot commands reference synced to Google Sheets!")
            else:
                await ctx.send("❌ Error syncing commands reference.")
                
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    @commands.command(name="plstats", aliases=["playliststats"])
    async def playlist_stats_cmd(self, ctx: commands.Context):
        """
        Show playlist and queue statistics.
        Usage: !plstats
        """
        try:
            from bot.music_sheets_sync import get_music_system_summary
            
            stats = get_music_system_summary()
            if not stats or 'catalog' not in stats:
                await ctx.send("Error loading music system statistics.")
                return
            
            catalog = stats['catalog']
            
            # Format top artists
            top_artists_str = ", ".join([f"{artist} ({count})" for artist, count in catalog['top_artists'][:3]])
            
            # Check current queue status
            try:
                # Try to get queue info from song request system
                from bot.commands.song_request_simple import song_manager
                queue_size = len(song_manager.current_queue) if hasattr(song_manager, 'current_queue') else 0
            except:
                queue_size = 0
            
            await ctx.send(
                f"🎵 **Music System:** {catalog['total_songs']} songs, {catalog['total_duration']} total, "
                f"{catalog['played_songs']} played, {catalog['unique_artists']} artists. "
                f"Queue: {queue_size} songs. Top: {top_artists_str}"
            )
            
        except Exception as e:
            await ctx.send(f"Error getting music stats: {str(e)}")

    @commands.command(name="srxcat", aliases=["srxcatalog"])
    async def srx_catalog_link(self, ctx: commands.Context):
        """Send the SRX catalog Google Sheet link."""
        await ctx.send("SRX Catalog: https://docs.google.com/spreadsheets/d/1vCFtktvfxNpaW4U1m9dJoBthS7n9HvYjfe2CYVHo134")

    @commands.command(name="cachestats", aliases=["cache"])
    async def cache_stats_cmd(self, ctx: commands.Context):
        """
        Show music cache statistics.
        Usage: !cachestats
        """
        try:
            from bot.commands.song_request_simple import song_manager
            
            cache_status = song_manager.get_cache_status()
            
            completion_percent = round((cache_status['cached_songs'] / cache_status['total_playlist_songs']) * 100, 1) if cache_status['total_playlist_songs'] > 0 else 0
            
            await ctx.send(
                f"🎵 **Cache Status:** {cache_status['cached_songs']}/{cache_status['total_playlist_songs']} songs cached ({completion_percent}%), "
                f"{cache_status['cache_size_mb']} MB total, {len(cache_status['missing_songs'])} missing, "
                f"{len(cache_status['orphaned_files'])} orphaned files"
            )
            
        except Exception as e:
            await ctx.send(f"Error getting cache stats: {str(e)}")

    @commands.command(name="cachediag", aliases=["cdiag"])
    async def cache_diagnostic_cmd(self, ctx: commands.Context):
        """
        Diagnose cache issues and identify potential problems.
        Usage: !cachediag
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can run cache diagnostics.")
            return

        try:
            from bot.commands.song_request_simple import song_manager
            import os
            
            cache_dir = "C:\\dev\\mean-gene-bot\\data\\music_cache"
            
            # Get actual files in cache
            if os.path.exists(cache_dir):
                cached_files = [f for f in os.listdir(cache_dir) 
                              if f.lower().endswith(('.m4a', '.webm', '.mp4', '.opus', '.ogg', '.mp3'))]
            else:
                cached_files = []
            
            # Get cache status
            cache_status = song_manager.get_cache_status()
            
            # Check for mismatches
            orphaned = cache_status.get('orphaned_files', [])
            missing = cache_status.get('missing_songs', [])
            
            diagnostic_msg = f"🔍 **Cache Diagnostics:**\n"
            diagnostic_msg += f"• Physical files: {len(cached_files)}\n"
            diagnostic_msg += f"• Playlist songs: {cache_status['total_playlist_songs']}\n"  
            diagnostic_msg += f"• Missing from cache: {len(missing)}\n"
            diagnostic_msg += f"• Orphaned files: {len(orphaned)}"
            
            if orphaned:
                diagnostic_msg += f"\n⚠️ Orphaned files (not in playlist): {', '.join(orphaned[:5])}"
                if len(orphaned) > 5:
                    diagnostic_msg += f" ... and {len(orphaned)-5} more"
            
            await ctx.send(diagnostic_msg)
            
        except Exception as e:
            await ctx.send(f"Error running diagnostics: {str(e)}")

    @commands.command(name="quickcache", aliases=["qcache"])
    async def quick_cache_cmd(self, ctx: commands.Context):
        """
        Smart cache recommendation based on current status.
        Usage: !quickcache
        """
        try:
            from bot.commands.song_request_simple import song_manager
            
            cache_status = song_manager.get_cache_status()
            missing_count = len(cache_status['missing_songs'])
            completion_percent = round((cache_status['cached_songs'] / cache_status['total_playlist_songs']) * 100, 1) if cache_status['total_playlist_songs'] > 0 else 0
            
            if missing_count == 0:
                await ctx.send("🎉 Perfect! All songs are cached. No action needed.")
            elif missing_count <= 10:
                await ctx.send(f"🎵 Almost there! Just {missing_count} songs missing. Try: !cachemissing {missing_count}")
            elif missing_count <= 50:
                await ctx.send(f"📥 {missing_count} songs missing ({completion_percent}% cached). Try: !cachemissing 20 or !cacheall")
            else:
                await ctx.send(f"🚀 {missing_count} songs missing ({completion_percent}% cached). Recommended: !cacheall (auto batch size)")
            
        except Exception as e:
            await ctx.send(f"Error analyzing cache: {str(e)}")

    @commands.command(name="cachemissing", aliases=["cachedown"])
    async def cache_missing_cmd(self, ctx: commands.Context, max_downloads: str = "10"):
        """
        Download missing playlist songs to cache (Moderator only).
        Usage: !cachemissing [max_downloads]
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can manage the music cache.")
            return

        try:
            max_num = int(max_downloads)
            if max_num <= 0 or max_num > 50:
                await ctx.send("Max downloads must be between 1 and 50.")
                return
        except ValueError:
            await ctx.send("Invalid number. Usage: !cachemissing [1-50]")
            return

        try:
            from bot.commands.song_request_simple import song_manager
            
            result = await song_manager.cache_missing_songs(max_num, ctx.channel)
            
            # Send final summary
            await ctx.send(f"📊 {result['message']}")
            
        except Exception as e:
            await ctx.send(f"Error caching songs: {str(e)}")

    @commands.command(name="cacheall", aliases=["fullcache"])
    async def cache_all_cmd(self, ctx: commands.Context, batch_size: str = None):
        """
        Cache the entire playlist in batches (Moderator only).
        Usage: !cacheall [batch_size] - defaults to smart batch size
        """
        # Check if user is a moderator
        if not (ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send("Only moderators can manage the music cache.")
            return

        # Smart default batch size based on missing songs
        if batch_size is None:
            try:
                from bot.commands.song_request_simple import song_manager
                cache_status = song_manager.get_cache_status()
                missing_count = len(cache_status['missing_songs'])
                
                if missing_count <= 20:
                    batch_num = 10  # Small batches for few songs
                elif missing_count <= 100:
                    batch_num = 15  # Medium batches
                else:
                    batch_num = 20  # Larger batches for many songs
                
                await ctx.send(f"🤖 Auto-selected batch size: {batch_num} (for {missing_count} missing songs)")
            except:
                batch_num = 15  # Safe default
        else:
            try:
                batch_num = int(batch_size)
                if batch_num <= 0 or batch_num > 50:
                    await ctx.send("Batch size must be between 1 and 50.")
                    return
            except ValueError:
                await ctx.send("Invalid number. Usage: !cacheall [1-50]")
                return

        try:
            from bot.commands.song_request_simple import song_manager
            
            # Get initial status for confirmation
            cache_status = song_manager.get_cache_status()
            missing_count = len(cache_status['missing_songs'])
            
            if missing_count == 0:
                await ctx.send("🎉 All playlist songs are already cached!")
                return
            
            await ctx.send(f"⚠️ This will download {missing_count} missing songs. This may take a while...")
            
            result = await song_manager.cache_all_playlist_songs(batch_num, ctx.channel)
            
            # Send final summary  
            await ctx.send(f"🎉 {result['message']} - Cache {result['cache_completion_percent']}% complete!")
            
        except Exception as e:
            await ctx.send(f"Error caching playlist: {str(e)}")

    @commands.command(name="queueinfo", aliases=["qinfo"])
    async def queue_info(self, ctx):
        """Show detailed queue information including duplicate prevention status"""
        try:
            from bot.commands.song_request_simple import song_manager
            
            queue = song_manager.current_queue
            if not queue:
                await ctx.send("📋 Queue is empty.")
                return
            
            total_songs = len(queue)
            max_queue = song_manager.max_queue_length
            
            message = f"📋 **Queue Status:** {total_songs}/{max_queue} songs\n\n"
            
            for i, (song_info, username, timestamp) in enumerate(queue[:10], 1):
                title = song_info.get('title', 'Unknown')
                artist = song_info.get('artist', 'Unknown')
                
                # Indicate if it's a playlist or YouTube song
                if song_info.get('number'):
                    indicator = f"🎵#{song_info['number']}"
                elif song_info.get('youtube_url'):
                    indicator = "🎬YT"
                else:
                    indicator = "❓"
                
                message += f"{i}. {indicator} {title} - {artist} (by {username})\n"
            
            if total_songs > 10:
                message += f"... and {total_songs - 10} more songs\n"
            
            message += f"\n💡 **Duplicate Prevention:** Active (prevents same songs from being queued twice)"
            
            await ctx.send(message)
            
        except Exception as e:
            await ctx.send(f"Error getting queue info: {str(e)}")

def prepare(bot: commands.Bot):
    """
    Adds the SongCog to the bot.
    """
    if not bot.get_cog("SongCog"):
        bot.add_cog(SongCog(bot))