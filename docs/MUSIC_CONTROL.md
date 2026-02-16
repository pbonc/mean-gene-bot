# 🎵 Music Playback & Volume Control System

## 🎛️ **Mod Music Controls**

Your song request system now has **full music playback control** with **automatic volume normalization**!

### **Core Music Commands (Mod Only):**

```bash
!music start     # Enable music system & start playing queue
!music stop      # Stop current song and disable system  
!music pause     # Pause current song
!music resume    # Resume paused song
!music next      # Skip to next song in queue
!music status    # Show current playback status

!volume 75       # Set volume to 75% (0-100)
!volume          # Check current volume level

!normalize       # Toggle volume normalization on/off
```

## 🔊 **Volume Equalization Features**

### **Automatic Volume Normalization:**
- ✅ **Downloads & normalizes** audio from YouTube automatically
- ✅ **Consistent volume** across all songs (no more quiet/loud surprises)
- ✅ **Smart caching** - downloads once, plays instantly after
- ✅ **FFmpeg integration** for professional audio processing

### **How It Works:**
1. **First Request**: Downloads YouTube audio → Normalizes volume → Caches locally
2. **Future Requests**: Plays instantly from normalized cache
3. **Consistent Experience**: All songs play at same perceived loudness

## 🎮 **Complete Workflow:**

### **Setup & Start:**
```bash
# Install audio dependencies (optional but recommended)
pip install pygame yt-dlp

# In chat (Mod commands):
!music start              # Enable music system
!volume 70               # Set comfortable volume
!normalize               # Ensure normalization is on
```

### **During Stream:**
```bash
# Viewers add songs:
Viewer: !srx 5           # Adds playlist song to queue

# Mod controls playback:
Mod: !music status       # Check what's playing
Mod: !music next         # Skip if needed  
Mod: !volume 80          # Adjust volume
Mod: !music pause        # Pause for announcements
Mod: !music resume       # Resume after break
```

## ⚡ **Smart Volume Handling:**

### **The Problem Solved:**
- YouTube videos have inconsistent audio levels
- Some songs are whisper-quiet, others blow your speakers
- Manual volume adjustment every song = bad UX

### **The Solution:**
- **Automatic normalization** to -16 LUFS (broadcast standard)
- **Peak limiting** prevents audio clipping  
- **Intelligent caching** for instant replay
- **Master volume control** for fine-tuning

## 🔧 **Technical Features:**

### **Audio Processing:**
- **Format**: High-quality MP3 (192kbps)
- **Normalization**: FFmpeg loudness normalization
- **Caching**: Local storage in `data/music_cache/`
- **Playback**: Pygame mixer with proper audio buffering

### **Volume Standards:**
- **Target LUFS**: -16 (streaming/broadcast standard)
- **Peak Limit**: -1.0dB (prevents clipping)
- **Dynamic Range**: Preserved within normalization

### **Cache Management:**
- **Location**: `data/music_cache/`
- **Format**: Normalized MP3 files
- **Benefit**: Instant playback after first download
- **Size**: Configurable max cache size (default 1GB)

## 🎯 **Chat Examples:**

```bash
# Starting music system:
Mod: !music start
Bot: 🎵 Music system enabled! Add songs to queue with !srx

# Adding songs & auto-play:
Viewer1: !srx 1
Bot: 🎬 Added #1: Bohemian Rhapsody by Queen (5:55) to queue (Position 1)
Bot: 🎵 Music started! Now playing: Bohemian Rhapsody (requested by Viewer1)

# Volume control:
Mod: !volume 80  
Bot: 🔊 Volume set to 80%.

# Playback control:
Mod: !music next
Bot: ⏭️ Skipped to next: Thunderstruck (requested by Viewer2)

Mod: !music status
Bot: 🎵 ▶️ Playing | Queue: 3 songs
     Now: Thunderstruck (by Viewer2)
```

## ⚙️ **Configuration:**

Edit `data/music_config.json` for advanced settings:

```json
{
  "audio_settings": {
    "master_volume": 0.7,
    "normalize_volume": true,
    "target_loudness_db": -16
  },
  "playback_settings": {
    "auto_play_queue": true,
    "fade_between_songs": true
  }
}
```

## 🚀 **Installation:**

### **Basic (Chat commands only):**
- Already working! No installation needed

### **Full Audio (Recommended):**
```bash
pip install pygame yt-dlp
```

### **Professional (With FFmpeg):**
1. Install FFmpeg for best audio processing
2. Audio normalization will be professional-grade
3. Better format support and processing

## 💡 **Pro Tips:**

### **For Streamers:**
- Start with `!volume 70` and adjust based on your setup
- Use `!music pause` during important announcements
- Check `!music status` to see queue length
- `!normalize` ensures consistent audio levels

### **For Viewers:**
- Playlist requests (`!srx 5`) are free and instant
- YouTube requests cost quarters but work with any video
- First-time YouTube songs may take a moment to process

**You now have professional-grade music control with automatic volume equalization!** 🎵🔊