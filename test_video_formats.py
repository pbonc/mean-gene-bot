"""
Test script to list available formats for a YouTube video
Usage: python test_video_formats.py <youtube_url>
"""

import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

try:
    import yt_dlp
    print("✅ yt-dlp imported successfully")
except ImportError as e:
    print(f"❌ yt-dlp import failed: {e}")
    sys.exit(1)

def test_video_formats(url):
    """Test and list all available formats for a YouTube video"""
    
    # Check for cookies file
    cookies_file = os.path.join(PROJECT_ROOT, "cookies.txt")
    has_cookies = os.path.exists(cookies_file)
    
    print(f"\n{'='*60}")
    print(f"Testing URL: {url}")
    print(f"Cookies file: {'✅ Found' if has_cookies else '❌ Not found'} ({cookies_file})")
    print(f"{'='*60}\n")
    
    # Setup options
    ydl_opts = {
        'quiet': False,
        'no_warnings': False,
        'socket_timeout': 30,
        'retries': 3,
        'listformats': True,  # List formats even if extraction fails
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-us,en;q=0.9',
        },
    }
    
    if has_cookies:
        ydl_opts['cookiefile'] = cookies_file
        print("🍪 Using cookies for authentication\n")
    
    try:
        print("Fetching video information...\n")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            print(f"\n{'='*60}")
            print(f"VIDEO INFORMATION")
            print(f"{'='*60}")
            print(f"Title: {info.get('title', 'N/A')}")
            print(f"Duration: {info.get('duration', 0)}s")
            print(f"Uploader: {info.get('uploader', 'N/A')}")
            print(f"View Count: {info.get('view_count', 'N/A')}")
            
            if 'formats' in info:
                print(f"\n{'='*60}")
                print(f"AVAILABLE FORMATS ({len(info['formats'])} total)")
                print(f"{'='*60}\n")
                
                # Group formats by type
                audio_only = []
                video_only = []
                combined = []
                
                for fmt in info['formats']:
                    format_id = fmt.get('format_id', 'N/A')
                    ext = fmt.get('ext', 'N/A')
                    
                    # Audio info
                    acodec = fmt.get('acodec', 'none')
                    abr = fmt.get('abr', 0)
                    asr = fmt.get('asr', 0)
                    
                    # Video info
                    vcodec = fmt.get('vcodec', 'none')
                    resolution = fmt.get('resolution', 'N/A')
                    fps = fmt.get('fps', 'N/A')
                    
                    format_note = fmt.get('format_note', '')
                    filesize = fmt.get('filesize', 0)
                    
                    fmt_info = {
                        'id': format_id,
                        'ext': ext,
                        'acodec': acodec,
                        'vcodec': vcodec,
                        'resolution': resolution,
                        'abr': abr,
                        'note': format_note,
                        'size': filesize if filesize else 'N/A'
                    }
                    
                    if acodec != 'none' and vcodec == 'none':
                        audio_only.append(fmt_info)
                    elif vcodec != 'none' and acodec == 'none':
                        video_only.append(fmt_info)
                    elif vcodec != 'none' and acodec != 'none':
                        combined.append(fmt_info)
                
                # Print audio-only formats (best for music bot)
                if audio_only:
                    print("🎵 AUDIO-ONLY FORMATS (Best for music):")
                    print("-" * 60)
                    for fmt in audio_only:
                        size_str = f"{fmt['size']/(1024*1024):.1f}MB" if isinstance(fmt['size'], (int, float)) else 'N/A'
                        print(f"  ID: {fmt['id']:<10} | Codec: {fmt['acodec']:<10} | "
                              f"Bitrate: {fmt['abr']:.0f}kbps | Size: {size_str}")
                
                # Print combined formats
                if combined:
                    print("\n🎬 COMBINED FORMATS (Video + Audio):")
                    print("-" * 60)
                    for fmt in combined:
                        size_str = f"{fmt['size']/(1024*1024):.1f}MB" if isinstance(fmt['size'], (int, float)) else 'N/A'
                        print(f"  ID: {fmt['id']:<10} | Resolution: {fmt['resolution']:<10} | "
                              f"Audio: {fmt['acodec']:<10} | Size: {size_str}")
                
                # Print video-only formats
                if video_only:
                    print("\n📹 VIDEO-ONLY FORMATS (No audio):")
                    print("-" * 60)
                    for fmt in video_only[:5]:  # Just show first 5
                        print(f"  ID: {fmt['id']:<10} | Resolution: {fmt['resolution']:<10} | "
                              f"Video: {fmt['vcodec']:<10}")
                
                # Best format recommendations
                print(f"\n{'='*60}")
                print("RECOMMENDED FORMAT STRINGS")
                print(f"{'='*60}")
                print("\nFor audio extraction (current bot uses 'best'):")
                print("  'bestaudio/best' - Best audio quality, fallback to best overall")
                print("  'bestaudio[ext=m4a]/bestaudio' - Prefer m4a audio")
                print("  'worstaudio' - Smallest file size")
                
                # Test specific format strings
                print(f"\n{'='*60}")
                print("TESTING FORMAT STRINGS")
                print(f"{'='*60}")
                
                test_formats = ['best', 'bestaudio/best', 'bestaudio', 'worstaudio']
                for fmt_str in test_formats:
                    test_opts = ydl_opts.copy()
                    test_opts['format'] = fmt_str
                    test_opts['quiet'] = True
                    test_opts['no_warnings'] = True
                    try:
                        with yt_dlp.YoutubeDL(test_opts) as test_ydl:
                            test_info = test_ydl.extract_info(url, download=False)
                            selected_format = test_info.get('format_id', 'N/A')
                            print(f"  '{fmt_str:<20}' -> Format ID: {selected_format} ✅")
                    except Exception as e:
                        print(f"  '{fmt_str:<20}' -> ❌ Error: {str(e)[:50]}")
                
            else:
                print("\n❌ No formats found in video info")
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_video_formats.py <youtube_url>")
        print("\nExample:")
        print("  python test_video_formats.py https://www.youtube.com/watch?v=hzFpiW5vHrc")
        sys.exit(1)
    
    url = sys.argv[1]
    test_video_formats(url)
