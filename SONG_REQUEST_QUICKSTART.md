# 🎵 Song Request System Quick Start

## What You Just Got:

### 🎯 **Core Commands**
- `!srx 5` - Request song #5 from your curated playlist (FREE)  
- `!srx https://youtube.com/watch?v=...` - Request YouTube song (costs 1 quarter)
- `!quarters` - Check your quarter balance
- `!queue` - See what songs are queued up

### 💰 **Quarter Economy** 
- **Playlist requests = FREE** (encourages your curated music)
- **YouTube requests = 1 quarter** (prevents spam, gives you control)
- Mods give quarters with `!givequarter username 5`

### 📋 **Your Playlist Setup**
Create a Google Sheet like this:

| A | B | C | D |
|---|---|---|---|
| **Number** | **Title** | **Artist** | **YouTube URL** |
| 1 | Bohemian Rhapsody | Queen | https://www.youtube.com/watch?v=fJ9rUzIMcZQ |
| 2 | Smells Like Teen Spirit | Nirvana | |
| 3 | Hotel California | Eagles | |

## 🚀 Quick Test (Without Setup)

The bot is ready to test right now! Here's what works immediately:

```
# This will work (fake playlist for testing):
!srx 1    # "Test Song #1"
!srx 2    # "Test Song #2" 
!queue    # Show what's queued
!quarters # Check your balance (probably 0)

# This needs quarters:
!srx https://youtube.com/watch?v=dQw4w9WgXcQ  # Will say "need more quarters"

# Mod gives quarters:
!givequarter yourname 3  # Mod command

# Now YouTube works:
!srx https://youtube.com/watch?v=dQw4w9WgXcQ  # Costs 1 quarter
```

## 🎮 The Flow You Wanted:

1. **Stream starts** → You have curated playlist in Google Sheet
2. **Viewers request** → `!srx 12` (free from your playlist)  
3. **Special requests** → `!srx [youtube_url]` (costs quarter)
4. **You control** → What's in playlist + who has quarters
5. **Chat engagement** → Free requests encourage playlist use

## ⚡ Next Steps:

1. **Test it now** - Commands work immediately with dummy data
2. **Create Google Sheet** - Follow the template above  
3. **Configure** - Update `data/song_request_config.json` with your sheet ID
4. **Optional Audio** - Install `pip install yt-dlp pygame` for playback integration

## 🔧 Mod Commands:
- `!playlist` - Refresh from Google Sheets
- `!givequarter username amount` - Give quarters  
- `!clearqueue` - Clear queue (to be added)
- `!skip` - Skip current song (to be added)

The system is **working right now** - just test the commands! The Google Sheet integration is optional for full functionality.