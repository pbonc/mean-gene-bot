# YouTube Cookie Authentication Setup

## Why You Need This

YouTube blocks too many anonymous requests from the same IP, causing **403 Forbidden** errors. Using authenticated cookies tells YouTube you're a logged-in user, which gives you higher rate limits and prevents these errors.

## How to Generate cookies.txt

### Method 1: Browser Extension (Easiest)

1. **Install Extension:**
   - Chrome/Edge: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. **Login to YouTube:**
   - Go to https://www.youtube.com
   - Sign in with your Google account

3. **Export Cookies:**
   - Click the extension icon
   - Click "Export" or "Get cookies.txt"
   - Save the file as `cookies.txt`

4. **Move to Bot Directory:**
   - Place `cookies.txt` in your bot's root directory:
     ```
     \dev\mean-gene-bot\cookies.txt
     ```

### Method 2: yt-dlp Command (Advanced)

```bash
yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## Verification

Once `cookies.txt` is in place, the bot will automatically use it for all YouTube requests. You'll see this in the logs:

```
Using cookies from C:\dev\mean-gene-bot\cookies.txt
```

## Security Notes

⚠️ **IMPORTANT:**
- `cookies.txt` contains your YouTube session - **DO NOT share it**
- **DO NOT commit it to git** (already in `.gitignore`)
- Cookies expire after a few months - regenerate if you get 403s again
- Use a throwaway Google account if you're paranoid

## Troubleshooting

**Still getting 403 errors?**
1. Regenerate cookies (they may have expired)
2. Make sure the file is named exactly `cookies.txt` (not `cookies.txt.txt`)
3. Check file is in the root directory: `\dev\mean-gene-bot\cookies.txt`
4. Restart the bot after adding cookies

**Bot not using cookies?**
- Check logs for "Using cookies from..." message
- Verify file path matches: `C:\dev\mean-gene-bot\cookies.txt`
- Make sure file isn't empty (should have multiple lines)

## What Changed

All yt-dlp operations now:
✅ Use standardized `get_ydl_opts()` function  
✅ Automatically load cookies if file exists  
✅ Use updated User-Agent (Chrome 120)  
✅ Respect download queue (one at a time)  
✅ Prevent concurrent request spikes

The bot will work without cookies, but may hit rate limits faster.
