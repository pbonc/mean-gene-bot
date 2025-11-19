import os
import sys
import subprocess
import importlib
import logging
from typing import List, Tuple, Dict

class DependencyManager:
    """Automatically check and install missing dependencies on bot startup"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.requirements_file = os.path.join(self.project_root, "requirements.txt")
        
        # Core dependencies (always install)
        self.core_dependencies = [
            "twitchio", "aiohttp", "discord.py", "gspread", 
            "google-auth", "python-dotenv", "pillow", "mutagen"
        ]
        
        # Optional dependencies (install if needed)
        self.optional_dependencies = {
            "pygame": "Audio playback for music system",
            "yt-dlp": "YouTube audio downloading and processing", 
            "ffmpeg-python": "Professional audio normalization",
            "playsound3": "Simple audio playback fallback"
        }
        
        # System dependencies that need special handling
        self.system_dependencies = {
            "ffmpeg": {
                "description": "Audio/video processing toolkit",
                "windows_install": "winget install ffmpeg",
                "linux_install": "sudo apt install ffmpeg",
                "check_command": "ffmpeg -version"
            }
        }

    def get_installed_packages(self) -> Dict[str, str]:
        """Get list of currently installed packages and versions"""
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                import json
                packages = json.loads(result.stdout)
                return {pkg["name"].lower().replace("-", "_"): pkg["version"] for pkg in packages}
        except Exception as e:
            self.logger.error(f"Error getting installed packages: {e}")
        return {}

    def read_requirements(self) -> List[str]:
        """Read requirements from requirements.txt"""
        try:
            if os.path.exists(self.requirements_file):
                with open(self.requirements_file, 'r') as f:
                    return [line.strip() for line in f.readlines() 
                           if line.strip() and not line.startswith('#')]
        except Exception as e:
            self.logger.error(f"Error reading requirements.txt: {e}")
        return []

    def check_import(self, package_name: str) -> bool:
        """Check if a package can be imported"""
        try:
            # Handle package name variations
            import_names = {
                "pillow": "PIL",
                "discord.py": "discord", 
                "google-auth": "google.auth",
                "python-dotenv": "dotenv",
                "ffmpeg-python": "ffmpeg",
                "yt-dlp": "yt_dlp"
            }
            
            import_name = import_names.get(package_name, package_name)
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False

    def install_package(self, package_name: str) -> Tuple[bool, str]:
        """Install a single package using pip"""
        try:
            self.logger.info(f"Installing {package_name}...")
            result = subprocess.run([sys.executable, "-m", "pip", "install", package_name], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                return True, f"Successfully installed {package_name}"
            else:
                return False, f"Failed to install {package_name}: {result.stderr}"
                
        except Exception as e:
            return False, f"Error installing {package_name}: {e}"

    def check_system_dependency(self, dep_name: str) -> bool:
        """Check if system dependency is available"""
        dep_info = self.system_dependencies.get(dep_name)
        if not dep_info:
            return True
        
        try:
            result = subprocess.run(dep_info["check_command"].split(), 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def install_missing_dependencies(self, force_install: bool = False) -> Dict[str, str]:
        """Check and install missing dependencies"""
        results = {}
        requirements = self.read_requirements()
        
        print("🔍 Checking dependencies...")
        
        # Check core dependencies first
        for package in self.core_dependencies:
            if package in requirements:
                if not self.check_import(package) or force_install:
                    print(f"📦 Installing core dependency: {package}")
                    success, message = self.install_package(package)
                    results[package] = "✅ " + message if success else "❌ " + message
                else:
                    results[package] = "✅ Already installed"
        
        # Check optional dependencies
        for package, description in self.optional_dependencies.items():
            if package in requirements:
                if not self.check_import(package):
                    print(f"🎵 Installing optional dependency: {package} ({description})")
                    success, message = self.install_package(package)
                    results[package] = "✅ " + message if success else "⚠️ " + message
                else:
                    results[package] = "✅ Already available"
        
        # Check system dependencies
        for dep_name, dep_info in self.system_dependencies.items():
            if not self.check_system_dependency(dep_name):
                system = "windows" if os.name == "nt" else "linux"
                install_cmd = dep_info.get(f"{system}_install", "Manual installation required")
                results[dep_name] = f"⚠️ Not found. Install with: {install_cmd}"
            else:
                results[dep_name] = "✅ Available"
        
        return results

    def get_dependency_status(self) -> Dict[str, Dict[str, str]]:
        """Get detailed status of all dependencies"""
        status = {
            "core": {},
            "optional": {},
            "system": {}
        }
        
        # Core dependencies
        for package in self.core_dependencies:
            available = self.check_import(package)
            status["core"][package] = "✅ Available" if available else "❌ Missing"
        
        # Optional dependencies  
        for package, description in self.optional_dependencies.items():
            available = self.check_import(package)
            status["optional"][package] = {
                "status": "✅ Available" if available else "⚠️ Missing",
                "description": description
            }
        
        # System dependencies
        for dep_name, dep_info in self.system_dependencies.items():
            available = self.check_system_dependency(dep_name)
            status["system"][dep_name] = {
                "status": "✅ Available" if available else "⚠️ Missing", 
                "description": dep_info["description"]
            }
        
        return status

    def print_status_report(self):
        """Print detailed dependency status report"""
        print("\n" + "="*60)
        print("🔧 DEPENDENCY STATUS REPORT")
        print("="*60)
        
        status = self.get_dependency_status()
        
        # Core dependencies
        print("\n📦 CORE DEPENDENCIES:")
        for package, status_msg in status["core"].items():
            print(f"   {status_msg} {package}")
        
        # Optional dependencies
        print("\n🎵 OPTIONAL DEPENDENCIES (Music Features):")
        for package, info in status["optional"].items():
            if isinstance(info, dict):
                print(f"   {info['status']} {package} - {info['description']}")
            else:
                print(f"   {info} {package}")
        
        # System dependencies
        print("\n🛠️ SYSTEM DEPENDENCIES:")
        for dep_name, info in status["system"].items():
            if isinstance(info, dict):
                print(f"   {info['status']} {dep_name} - {info['description']}")
            else:
                print(f"   {info} {dep_name}")
        
        print("\n" + "="*60)

def auto_install_dependencies():
    """Main function to auto-install dependencies on bot startup"""
    print("🚀 Starting dependency check...")
    
    manager = DependencyManager()
    
    # Show current status
    manager.print_status_report()
    
    # Ask user if they want to install missing dependencies
    try:
        choice = input("\n📥 Install missing dependencies? (Y/n): ").lower().strip()
        if choice in ['', 'y', 'yes']:
            results = manager.install_missing_dependencies()
            
            print("\n📋 INSTALLATION RESULTS:")
            print("-" * 40)
            for package, result in results.items():
                print(f"   {result}")
            
            print("\n🎉 Dependency installation complete!")
            return True
        else:
            print("⏭️ Skipping dependency installation.")
            return False
            
    except KeyboardInterrupt:
        print("\n⏹️ Installation cancelled by user.")
        return False

# For command line usage
if __name__ == "__main__":
    auto_install_dependencies()