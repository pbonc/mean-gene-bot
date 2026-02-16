# YouTube 403/Format Error Fix - February 2026

## The Problem

You were getting this error:
```
ERROR: [youtube] hzFpiW5vHrc: Requested format is not available. Use --list-formats for a list of available formats
```

## Root Cause

When we ran `--list-formats`, we discovered that YouTube was only returning **storyboard images** (thumbnails) instead of actual audio/video formats. This happened because:

1. **Signature solving failed** - yt-dlp couldn't decrypt the video URLs
2. **n challenge solving failed** - YouTube's anti-bot challenge system blocked access
3. **Only 4 image formats available** - No actual downloadable audio/video

This is YouTube's new anti-bot protection system that started in late 2024, requiring:
- JavaScript runtime to solve signature challenges
- "PO Tokens" (Proof of Origin tokens) for certain clients
- Complex challenge-response systems

## The Solution

I've implemented a **two-tier download strategy**:

### Tier 1: Normal Download (with cookies)
- Uses web client with cookies
- Best quality and features
- Works for most videos

### Tier 2: Android Client Fallback (no cookies)
- If Tier 1 fails with format/signature errors, automatically retry with Android client
- Bypasses signature challenges
- Lower quality but more reliable
- No cookie support (Android client limitation)

## Changes Made

### 1. Updated `get_ydl_opts()` function
- Added `use_android_client` parameter
- Changed format from `'best'` to `'bestaudio/best'` (more reliable)
- When Android client is used, cookies are disabled (Android client doesn't support them)

### 2. Updated `_queue_download_song()` function
- First attempts download with normal options (cookies, web client)
- If format/signature errors occur, automatically retries with Android client
- Lists available formats if both attempts fail (for debugging)

### 3. Created `test_video_formats.py` script
- Manually test any YouTube URL
- Shows all available formats
- Tests different format strings
- Usage: `python test_video_formats.py <youtube_url>`

## Testing the Fix

Test the problematic video:
```powershell
python test_video_formats.py "https://www.youtube.com/watch?v=hzFpiW5vHrc"
```

Or test with yt-dlp directly:
```powershell
# Android client (works for restricted videos)
yt-dlp --extractor-args "youtube:player_client=android" -f "bestaudio/best" "URL"

# Normal (with cookies)
yt-dlp --cookies cookies.txt -f "bestaudio/best" "URL"
```

## What Happens Now

When the bot tries to download a song:

1. **First Attempt**: Uses web client + cookies (best quality)
2. **If Format Error**: Automatically retries with Android client
3. **If Still Fails**: Logs available formats and gives up

The bot will now automatically handle videos that were previously failing with format errors!

## Known Limitations

- **Android client**: Lower quality formats, no cookies, may have geo-restrictions
- **PO Tokens**: Some videos may still require PO tokens (extremely rare)
- **Age-restricted videos**: May still fail even with Android client

## Future Improvements (if needed)

If you encounter more issues:
1. **PO Token generation**: Implement automated PO token fetching
2. **iOS client**: Add as third fallback tier
3. **Format selection**: Add smarter format selection based on available formats
4. **Rate limiting**: Implement better rate limiting for YouTube requests

## The Error You'll See Now

Instead of just failing, the bot will now:
1. Log: "Format/signature error, retrying with Android client..."
2. Try Android client
3. Log: "✅ Android client download succeeded" (if successful)
4. Or list available formats if both fail (for debugging)
