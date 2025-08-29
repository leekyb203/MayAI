#!/usr/bin/env python3
"""
May AI Learning System - Easy Startup Script
Run this file to start May's learning interface
"""

import subprocess
import sys
import os
import time

def install_requirements():
    """Install required packages"""
    requirements = [
        "fastapi==0.104.1",
        "uvicorn==0.24.0", 
        "aiohttp==3.9.1",
        "beautifulsoup4==4.12.2",
        "python-multipart==0.0.6",
        "jinja2==3.1.2"
    ]
    
    print("🔧 Installing requirements...")
    for req in requirements:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", req])
        except subprocess.CalledProcessError:
            print(f"⚠️  Failed to install {req}")
    print("✅ Requirements installed!")

def create_directories():
    """Create necessary directories"""
    directories = ["templates", "data", "logs"]
    for dir_name in directories:
        os.makedirs(dir_name, exist_ok=True)
    print("✅ Directories created!")

def check_and_run():
    """Check setup and run May"""
    print("🤖 Starting May AI Learning System...")
    print("=" * 50)
    
    # Install requirements
    install_requirements()
    
    # Create directories
    create_directories()
    
    # Import and run the main application
    try:
        print("🚀 Starting web interface...")
        print("📱 Access May's dashboard at: http://localhost:8000")
        print("🛑 Press Ctrl+C to stop")
        print("=" * 50)
        
        # Import the fixed web interface (all-in-one file)
        import web_interface_fixed
        
    except KeyboardInterrupt:
        print("\n👋 May AI Learning System stopped.")
    except Exception as e:
        print(f"❌ Error starting May: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure you have Python 3.7+")
        print("2. Check your internet connection") 
        print("3. Try running: pip install --upgrade pip")

if __name__ == "__main__":
    check_and_run()