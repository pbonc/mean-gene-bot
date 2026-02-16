#!/usr/bin/env python3
"""
Binary Playlist Decoder for Mean Gene Bot
Attempts to decode various binary playlist formats
"""

import struct
import json
import os
import sys
import re
from pathlib import Path

class BinaryPlaylistDecoder:
    def __init__(self, file_path):
        self.file_path = file_path
        self.songs = []
        
    def read_binary_file(self):
        """Read binary file and attempt various decoding methods"""
        try:
            with open(self.file_path, 'rb') as f:
                self.data = f.read()
            print(f"📁 Loaded {len(self.data)} bytes from {self.file_path}")
            return True
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False
    
    def extract_strings(self, min_length=4):
        """Extract readable strings from binary data"""
        strings = []
        
        # Try different encodings
        encodings = ['utf-8', 'utf-16', 'latin1', 'cp1252']
        
        for encoding in encodings:
            try:
                decoded = self.data.decode(encoding, errors='ignore')
                # Find strings that look like file paths, URLs, or titles
                patterns = [
                    r'[a-zA-Z]:[\\\/][^\\\/\x00-\x1f]+',  # Windows paths
                    r'https?://[^\s\x00-\x1f]+',  # URLs
                    r'[a-zA-Z0-9\s\-_\'\"()]{4,}',  # General text
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, decoded)
                    for match in matches:
                        if len(match) >= min_length and match not in strings:
                            strings.append(match.strip('\x00\r\n'))
                            
            except Exception as e:
                continue
        
        return [s for s in strings if len(s.strip()) >= min_length]
    
    def extract_urls_and_titles(self):
        """Extract URLs and potential song titles from strings"""
        strings = self.extract_strings()
        
        urls = []
        titles = []
        
        for string in strings:
            # Check for URLs
            if any(domain in string.lower() for domain in ['youtube.com', 'youtu.be', 'spotify.com', 'soundcloud.com']):
                urls.append(string)
            # Check for file paths with music extensions
            elif any(ext in string.lower() for ext in ['.mp3', '.wav', '.flac', '.m4a', '.wma', '.ogg']):
                # Extract filename as potential title
                filename = os.path.basename(string)
                title = os.path.splitext(filename)[0]
                titles.append(title)
            # Check for strings that might be song titles
            elif len(string) > 10 and len(string) < 100:
                # Heuristic: contains letters and might be a title
                if re.match(r'^[a-zA-Z0-9\s\-_\'\"()&!.]+$', string):
                    titles.append(string)
        
        return urls, titles
    
    def try_structured_parsing(self):
        """Try to parse as structured binary formats"""
        # Try common binary playlist formats
        
        # Check for WPL (Windows Media Player) format
        if b'<?wpl' in self.data[:100]:
            return self.parse_wpl()
            
        # Check for ASX format
        if b'<asx' in self.data[:100]:
            return self.parse_asx()
            
        # Check for iTunes binary format
        if b'iTunes' in self.data[:100]:
            return self.parse_itunes()
            
        return []
    
    def parse_wpl(self):
        """Parse Windows Media Player playlist"""
        try:
            # Convert to string and parse XML-like structure
            text = self.data.decode('utf-8', errors='ignore')
            # Extract media entries
            media_pattern = r'<media src="([^"]+)"'
            matches = re.findall(media_pattern, text, re.IGNORECASE)
            return matches
        except:
            return []
    
    def decode_playlist(self):
        """Main decoding function"""
        if not self.read_binary_file():
            return []
        
        print("🔍 Analyzing binary playlist format...")
        
        # Try structured parsing first
        structured_results = self.try_structured_parsing()
        if structured_results:
            print(f"✅ Found {len(structured_results)} entries using structured parsing")
            return structured_results
        
        # Fall back to string extraction
        print("📝 Extracting strings from binary data...")
        urls, titles = self.extract_urls_and_titles()
        
        print(f"🔗 Found {len(urls)} URLs")
        print(f"🎵 Found {len(titles)} potential song titles")
        
        # Combine results
        results = []
        
        # Add URLs first (highest confidence)
        for url in urls:
            results.append({
                'type': 'url',
                'value': url,
                'confidence': 'high'
            })
        
        # Add titles
        for title in titles[:50]:  # Limit to 50 to avoid spam
            results.append({
                'type': 'title',
                'value': title,
                'confidence': 'medium'
            })
        
        return results
    
    def print_results(self, results):
        """Print decoded results"""
        if not results:
            print("❌ No playlist entries found")
            return
        
        print(f"\n📋 Extracted {len(results)} playlist entries:")
        print("=" * 50)
        
        for i, result in enumerate(results[:20], 1):  # Show first 20
            confidence = result.get('confidence', 'unknown')
            result_type = result.get('type', 'unknown')
            value = result.get('value', result)
            
            if isinstance(value, dict):
                value = str(value)
                
            print(f"{i:2d}. [{result_type.upper():5s}] {value}")
        
        if len(results) > 20:
            print(f"    ... and {len(results) - 20} more entries")

def main():
    if len(sys.argv) != 2:
        print("Usage: python binary_playlist_decoder.py <playlist_file>")
        return
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    print("🎵 Binary Playlist Decoder for Mean Gene Bot")
    print("=" * 50)
    print(f"📁 File: {file_path}")
    print(f"📏 Size: {os.path.getsize(file_path)} bytes")
    
    decoder = BinaryPlaylistDecoder(file_path)
    results = decoder.decode_playlist()
    decoder.print_results(results)

if __name__ == "__main__":
    main()