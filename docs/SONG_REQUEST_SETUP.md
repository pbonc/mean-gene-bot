# Song Request System Setup

## 📋 Google Sheets Playlist Template

Create a Google Sheet with the following columns:

| Column A | Column B | Column C | Column D |
|----------|----------|----------|----------|
| Number | Title | Artist | YouTube URL (Optional) |
| 1 | Bohemian Rhapsody | Queen | https://www.youtube.com/watch?v=fJ9rUzIMcZQ |
| 2 | Smells Like Teen Spirit | Nirvana | |
| 3 | Hotel California | Eagles | |
| 4 | Stairway to Heaven | Led Zeppelin | |
| 5 | Sweet Child O' Mine | Guns N' Roses | |

## 🔧 Setup Instructions

### 1. Google Sheets Setup
1. Create a new Google Sheet
2. Set up columns as shown above
3. Add your curated playlist
4. Share the sheet (make it readable by anyone with link)
5. Copy the Sheet ID from the URL
6. Update `song_request_config.json` with your sheet ID

### 2. Bot Configuration
Update your `song_request_config.json`:
```json
{
  "sheet_id": "YOUR_GOOGLE_SHEET_ID_HERE",
  "range": "A:D",
  "settings": {
    "quarters_per_youtube_request": 1,
    "max_queue_length": 10,
    "max_song_duration_seconds": 300
  }
}
```

### 3. Install Dependencies (Optional)
For full functionality, install these packages:
```bash
pip install yt-dlp pygame
```

## 🎵 Commands

### Viewer Commands
- `!srx 5` - Request song #5 from playlist (free)
- `!srx https://youtube.com/watch?v=...` - Request YouTube song (costs 1 quarter)
- `!quarters` - Check your quarters
- `!queue` - See current song queue

### Mod Commands  
- `!playlist` - Refresh playlist from Google Sheets
- `!givequarter [username] [amount]` - Give quarters to users
- `!clearqueue` - Clear song queue (to be added)
- `!skip` - Skip current song (to be added)

## 💰 Quarter System

**Earning Quarters:**
- Mods can give quarters with `!givequarter`
- Future: Integrate with channel points, follows, subs, etc.

**Spending Quarters:**
- YouTube requests cost 1 quarter
- Playlist requests are free
- Encourages use of curated playlist

## 🎮 Usage Flow

1. **Setup Phase:** Create Google Sheet with your playlist
2. **Stream Phase:** Viewers request songs using numbers or YouTube URLs
3. **Management:** You control what's in the playlist via Google Sheets
4. **Currency:** Quarters limit YouTube spam, encourage playlist use

## 📝 Example Chat Usage

```
Viewer1: !srx 12
Bot: 🎵 Added #12: Thunderstruck by AC/DC to queue (Position 1)

Viewer2: !srx https://youtube.com/watch?v=dQw4w9WgXcQ  
Bot: ❌ You need 1 more quarter to request YouTube songs. You have 0.

Mod: !givequarter Viewer2 2
Bot: 💰 Gave 2 quarters to Viewer2.

Viewer2: !srx https://youtube.com/watch?v=dQw4w9WgXcQ
Bot: 🔄 Processing YouTube request...
Bot: 🎵 Added YouTube: Never Gonna Give You Up (3:32) to queue (Position 2) [-1 quarter]
```

## 🔮 Future Enhancements

- **Audio Playback:** Integrate with OBS or streaming software
- **Auto-Skip:** Skip explicit content or enforce time limits  
- **Point Integration:** Earn quarters from Twitch Channel Points
- **Voting System:** Let chat vote to skip songs
- **History Tracking:** Remember popular requests
- **Smart Shuffle:** Auto-play from playlist when queue is empty