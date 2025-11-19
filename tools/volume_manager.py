import json
import os
from typing import Dict, Any

# Simple volume management without external dependencies
class VolumeManager:
    """Simplified volume management for immediate use"""
    
    def __init__(self):
        self.config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "music_config.json"
        )
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict[str, Any]:
        """Load music configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading music config: {e}")
        
        # Default settings
        return {
            "audio_settings": {
                "master_volume": 0.7,
                "normalize_volume": True,
                "target_loudness_db": -16
            },
            "playback_settings": {
                "auto_play_queue": True,
                "auto_start_on_first_request": False
            }
        }
    
    def save_settings(self):
        """Save music configuration"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving music config: {e}")
    
    def get_volume_multipliers(self) -> Dict[str, float]:
        """Get volume multipliers for common problematic songs/artists"""
        # Common volume adjustments for popular songs that are known to be too quiet/loud
        return {
            # Quiet songs that need boosting (multiply by >1.0)
            "bohemian_rhapsody": 1.3,
            "hotel_california": 1.2,
            "stairway_to_heaven": 1.4,
            "imagine": 1.5,
            "the_sound_of_silence": 1.6,
            
            # Loud songs that need reducing (multiply by <1.0)  
            "thunderstruck": 0.7,
            "welcome_to_the_jungle": 0.8,
            "back_in_black": 0.7,
            "smells_like_teen_spirit": 0.8,
            "enter_sandman": 0.6,
            
            # Modern pop/rock (often compressed loud)
            "uptown_funk": 0.7,
            "shape_of_you": 0.8,
            "bad_guy": 0.9,
            
            # Classical/acoustic (often quiet)
            "claire_de_lune": 1.8,
            "moonlight_sonata": 1.6,
            "the_four_seasons": 1.4,
        }
    
    def get_song_volume_adjustment(self, song_title: str) -> float:
        """Get volume adjustment for specific song"""
        multipliers = self.get_volume_multipliers()
        
        # Normalize title for matching
        normalized_title = song_title.lower().replace(" ", "_")
        normalized_title = "".join(c for c in normalized_title if c.isalnum() or c == "_")
        
        # Check for partial matches
        for song_key, multiplier in multipliers.items():
            if song_key in normalized_title or any(word in normalized_title for word in song_key.split("_")):
                return multiplier
        
        # Default multiplier
        return 1.0
    
    def suggest_volume_fix(self, song_title: str, artist: str = "") -> str:
        """Suggest volume adjustment for a song"""
        adjustment = self.get_song_volume_adjustment(song_title)
        
        if adjustment > 1.2:
            return f"🔊 '{song_title}' tends to be quiet - consider boosting volume"
        elif adjustment < 0.8:
            return f"🔉 '{song_title}' tends to be loud - consider reducing volume" 
        else:
            return f"🎵 '{song_title}' should play at normal volume"

# Example usage and testing
if __name__ == "__main__":
    vm = VolumeManager()
    
    test_songs = [
        "Bohemian Rhapsody",
        "Thunderstruck", 
        "Hotel California",
        "Welcome to the Jungle",
        "Imagine",
        "Random Song Title"
    ]
    
    print("🎵 Volume Adjustment Suggestions:")
    print("=" * 50)
    
    for song in test_songs:
        suggestion = vm.suggest_volume_fix(song)
        adjustment = vm.get_song_volume_adjustment(song)
        print(f"{suggestion} (×{adjustment})")