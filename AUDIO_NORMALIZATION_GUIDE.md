# 🔊 Audio Normalization Implementation Guide

## Overview

The bot now includes **automatic FFmpeg-based loudness normalization** for all downloaded songs, ensuring consistent volume levels across your playlist. This solves the problem of songs being whisper-quiet or dangerously loud.

## How It Works

### Automatic Normalization on Download
When songs are downloaded (both for initial requests and caching):
1. **Download** - Song is fetched from YouTube using yt-dlp
2. **Normalize** - FFmpeg applies loudness normalization filter
3. **Cache** - Normalized file is stored locally for instant future playback

### Normalization Parameters
- **Target Loudness**: -16 LUFS (integrated loudness)
- **True Peak Limit**: -1.0 dB (prevents audio clipping)
- **Loudness Range**: 11.0 dB (preserves dynamic range)
- **Output Format**: High-quality MP3 (192kbps, quality 9)

These are broadcast-standard settings used by Netflix, YouTube, and professional streaming services.

## New Commands

### Normalize Specific Song
```
!normalizecache [number]
```
Normalizes a single song by catalog number. Useful if you added a song before the normalization feature was implemented.

**Example:**
```
Mod: !normalizecache 42
Bot: 🔊 Normalizing song #42: Bohemian Rhapsody...
Bot: ✅ Normalized #42: Bohemian Rhapsody to -16 LUFS
```

### Normalize All Cached Songs
```
!normalizecache
```
Normalizes all cached songs in the music_cache directory. This is useful for equalizing songs that were downloaded before this feature existed.

**Example:**
```
Mod: !normalizecache
Bot: 🔊 Starting normalization of all cached songs...
Bot: ⏳ This may take several minutes depending on cache size. I'll update you as songs are completed.
Bot: 📦 Found 127 cached files to normalize...
Bot: 📥 Progress: 5/127 songs normalized...
Bot: 📥 Progress: 10/127 songs normalized...
[... continues with progress updates ...]
Bot: ✅ Normalization complete!
Bot: 🎵 Normalized: 127/127 songs
```

## Usage Workflow

### For Streamers
1. **Enable normalization** - Automatically active on all new downloads
2. **Normalize existing songs** (optional) - Run `!normalizecache` once to normalize previously downloaded songs
3. **Enjoy consistent audio** - All songs now play at the same perceived loudness

### For Mods
- Use `!modmusic` to see available commands including normalization options
- Run `!normalizecache [number]` to fix individual songs
- Run `!normalizecache` during low-activity periods to normalize entire cache

## Technical Details

### FFmpeg Integration
- **Location**: `C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe`
- **Filter**: `loudnorm=I=-16:TP=-1.0:LRA=11.0`
- **Processing**: Runs synchronously during normalization, uses executor for async compatibility

### File Handling
- **Input Formats Supported**: MP3, M4A, WebM, MP4, Opus, OGG
- **Output Format**: MP3 (all files standardized to MP3)
- **Processing**: 
  - Creates temporary normalized file
  - Validates successful processing
  - Replaces original with normalized version
  - Cleans up temporary files on failure

### Cache Directory
- **Location**: `data/music_cache/`
- **File Naming**: Safe title with extension (e.g., `Song_Title.mp3`)
- **Organization**: All audio files in single directory

## Configuration

Edit `data/music_config.json` to adjust normalization parameters:

```json
{
  "volume_normalization": {
    "enabled": true,
    "method": "ffmpeg_loudnorm",
    "target_lufs": -16,
    "peak_db": -1.0,
    "range_db": 11.0
  }
}
```

### Parameter Explanations
- **target_lufs** (-16): Integrated loudness in LUFS (Loudness Units relative to Full Scale)
- **peak_db** (-1.0): Maximum peak to prevent distortion/clipping
- **range_db** (11.0): Loudness range to preserve dynamic range

## Behavior

### When Downloading
- New requests automatically apply normalization
- Users see no delay (normalization happens during download)
- Failed normalization doesn't block playback (file still plays)

### When Batch Normalizing
- Updates every 5 files to show progress
- Continues even if individual files fail
- Gives final summary with success/failure counts

### Error Handling
- Supports multiple audio formats (MP3, M4A, WebM, etc.)
- Validates FFmpeg execution
- Cleans up temporary files on failure
- Logs detailed error information

## Performance Impact

- **New Downloads**: ~5-10 seconds additional time (depends on song length)
- **Batch Normalization**: ~30-60 seconds per song (can run in background)
- **Playback**: No impact (files are pre-normalized)

## Troubleshooting

### Command Not Found
```
❌ Only mods can normalize audio files.
```
- Ensure you're a mod or broadcaster
- Use `!modmusic` to verify command availability

### File Not Found
```
❌ Song #42 not in cache. Download it first with !srx 42
```
- Download the song with `!srx 42` first
- Then normalize with `!normalizecache 42`

### Normalization Fails
```
⚠️ Normalization completed for #42, but with warnings
```
- File may still be playable despite normalization issues
- Check logs for detailed error information
- Try re-downloading the song

### FFmpeg Not Found
```
Error normalizing audio: [Errno 2] No such file or directory
```
- Verify FFmpeg is installed at `C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe`
- Update the path in `song_request_simple.py` if installed elsewhere

## Advanced Usage

### Normalize During Caching Batch
When running `!cacheall` or `!cachemissing`, new songs are automatically normalized as they're downloaded.

### Manual Normalization
To normalize without re-downloading:
```python
from bot.commands.song_request_simple import song_manager
song_manager.normalize_audio_file('/path/to/audio.mp3')
```

### Checking Audio Properties
FFmpeg provides loudness analysis. For detailed before/after metrics:
```bash
ffmpeg -i input.mp3 -af loudnorm=I=-16:TP=-1.0:LRA=11.0 -f null -
```

## Volume Control Hierarchy

1. **Normalization** (uniform across songs): -16 LUFS
2. **Master Volume** (global control): !volume command
3. **System Volume**: OS/Discord/Browser settings

All levels work together for optimal audio balance.

## Related Commands

- `!music start/stop` - Control playback
- `!volume [0-100]` - Set master volume level
- `!cacheall` - Download and normalize entire playlist
- `!cachemissing` - Download and normalize missing songs
- `!modmusic` - Show all mod commands

## Summary

✅ **Automatic normalization** on all new downloads  
✅ **Batch normalize** existing cache with one command  
✅ **Normalize individual songs** by catalog number  
✅ **Broadcast-standard** audio quality (-16 LUFS)  
✅ **Error handling** and logging for troubleshooting  

Your stream now has professional-grade audio normalization! 🎵🔊
