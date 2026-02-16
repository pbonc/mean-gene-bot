# 🔊 Audio Normalization - Quick Start

## What Changed

Your song request bot now has **automatic audio normalization** to fix the volume inconsistency problem.

## For New Downloads
✅ All songs downloaded now are automatically normalized to -16 LUFS  
✅ No extra steps needed - it happens during download  
✅ Songs play immediately after normalization  

## For Existing Cached Songs
You have two commands:

### Normalize One Song by Number
```
!normalizecache 42
```
Normalizes song #42 to standard -16 LUFS volume level.

### Normalize All Cached Songs
```
!normalizecache
```
Normalizes your entire music cache (all 100+ songs).
- Shows progress updates every 5 songs
- Takes a few minutes depending on cache size
- You can run it overnight or during off-hours

## The Numbers Behind It

| Setting | Value | Purpose |
|---------|-------|---------|
| Target Loudness | -16 LUFS | Broadcast standard (Netflix, YouTube) |
| Peak Limit | -1.0 dB | Prevents distortion/clipping |
| Dynamic Range | 11.0 dB | Preserves music quality |

## What This Solves

### Before 🔊❌
- Some songs are whisper-quiet
- Others blow out your speakers
- Constant manual volume adjustment
- Unprofessional listener experience

### After 🔊✅
- All songs play at same perceived loudness
- No more surprise volume jumps
- Professional broadcast-standard audio
- Better viewer experience

## Under the Hood

**Technology**: FFmpeg loudnorm filter  
**Processing**: Happens during download (no extra time for future plays)  
**Format**: All songs standardized to MP3 (192kbps)  
**Caching**: Normalized files stored in `data/music_cache/`

## Need Help?

**Command not working?**  
- Ensure you're a mod/broadcaster
- Check `!modmusic` to see available commands

**Normalization failed?**  
- File is still playable even if normalization warns
- Check bot logs for detailed error messages

**Want to adjust settings?**  
- Edit `data/music_config.json` to change target LUFS, peak, etc.
- Restart bot for changes to take effect

## Example Usage

```
Mod: !normalizecache
Bot: 🔊 Starting normalization of all cached songs...
Bot: ⏳ This may take several minutes depending on cache size.
Bot: 📦 Found 127 cached files to normalize...
Bot: 📥 Progress: 5/127 songs normalized...
Bot: 📥 Progress: 10/127 songs normalized...
[... waits ...]
Bot: ✅ Normalization complete!
Bot: 🎵 Normalized: 127/127 songs
```

---

**Result**: All 127 songs now play at consistent -16 LUFS volume! 🎵✨
