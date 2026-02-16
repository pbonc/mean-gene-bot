# 🚀 **Automatic Dependency Installation Guide**

## ✅ **Updated Requirements.txt**

Your `requirements.txt` now includes all music system dependencies:

```
twitchio              # Twitch bot framework
aiohttp               # HTTP requests  
discord.py            # Discord integration
gspread               # Google Sheets sync
google-auth           # Google authentication
python-dotenv         # Environment variables
pillow                # Image processing
mutagen               # Audio metadata
playsound3            # Basic audio playback
pygame                # Advanced audio playback 🎵
yt-dlp                # YouTube downloading 🎵
ffmpeg-python         # Audio processing 🎵
pytz                  # Timezone handling
```

## 🔧 **3 Ways to Install Dependencies**

### **Method 1: Automatic Startup (Recommended)**

**Windows:**
```bash
# Just double-click this file:
start_bot.bat
```

**Linux/Mac:**
```bash
# Run this command:
./start_bot.sh
```

The startup script will:
- ✅ Check Python installation
- ✅ Create virtual environment if needed
- ✅ Auto-install missing dependencies
- ✅ Check configuration files
- ✅ Start the bot

### **Method 2: Manual Installation**

```bash
# Install all dependencies at once:
pip install -r requirements.txt

# Or install music dependencies separately:
pip install pygame yt-dlp ffmpeg-python
```

### **Method 3: Auto-Install on Bot Start**

Add this to your `.env` file:
```
AUTO_INSTALL_DEPENDENCIES=true
```

The bot will automatically install missing dependencies every time it starts.

## 🎵 **Dependency Tiers**

### **Core Dependencies (Always Required):**
- `twitchio`, `aiohttp`, `discord.py` - Bot functionality
- `gspread`, `google-auth` - Google Sheets integration
- `python-dotenv`, `pillow` - Configuration & image processing

### **Music Dependencies (Optional but Recommended):**
- `pygame` - Audio playback system
- `yt-dlp` - YouTube video downloading
- `ffmpeg-python` - Professional audio processing

### **System Dependencies:**
- **FFmpeg** - Audio/video processing toolkit
  - Windows: `winget install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
  - Mac: `brew install ffmpeg`

## 🔍 **Dependency Checker Tool**

Run the dependency checker manually:
```bash
python -m bot.dependency_manager
```

This will:
- ✅ Check what's installed vs missing
- 🎵 Show which music features are available
- 💡 Offer to install missing packages
- 📊 Display detailed status report

## 🎮 **What Happens Without Music Dependencies**

| Dependency | Without It | With It |
|------------|------------|---------|
| **pygame** | Song requests work, no audio | Full audio playback |
| **yt-dlp** | No YouTube processing | Download & normalize audio |
| **ffmpeg** | Basic audio only | Professional volume normalization |

## ⚡ **Quick Start Workflow**

1. **Download/Clone** the bot
2. **Double-click** `start_bot.bat` (Windows) or run `./start_bot.sh` (Linux/Mac)
3. **Follow prompts** to install dependencies
4. **Create .env** file with your tokens if needed
5. **Bot starts** with all features ready!

## 🔧 **Advanced Configuration**

### **Environment Variables for Auto-Install:**
```bash
# .env file options:
AUTO_INSTALL_DEPENDENCIES=true    # Auto-install on startup
SKIP_DEPENDENCY_CHECK=false       # Skip all dependency checks
MUSIC_SYSTEM_ENABLED=true         # Enable music features
```

### **Dependency Manager Settings:**
The system automatically:
- ✅ Installs core dependencies (required for bot)
- ⚠️ Asks before installing optional dependencies  
- 📊 Shows detailed status reports
- 💾 Remembers installation preferences

## 🎯 **Perfect Setup Process**

### **First Time Setup:**
```bash
# 1. Clone/download bot
git clone [repository]
cd mean-gene-bot

# 2. Run startup script (installs everything)
start_bot.bat          # Windows
./start_bot.sh         # Linux/Mac

# 3. Create .env file with your tokens
# 4. Bot starts with full music system!
```

### **Daily Usage:**
```bash
# Just run the startup script - it handles everything:
start_bot.bat
```

## ✨ **What You Get**

After running the startup script, you'll have:

- ✅ **Complete bot functionality** (chat commands, overlays, etc.)
- 🎵 **Full music system** with volume normalization
- 📊 **Dependency status monitoring** 
- 🔄 **Automatic updates** for missing packages
- 🛠️ **Professional audio processing** with FFmpeg
- 💾 **Virtual environment** for clean installation

**Your bot now installs its own dependencies automatically!** 🚀✨