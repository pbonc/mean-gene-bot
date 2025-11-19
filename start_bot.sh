#!/bin/bash

# Mean Gene Bot Startup Script for Linux/Mac

echo "========================================"
echo "   🤖 Mean Gene Bot Startup Script"
echo "========================================"
echo

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    echo "   Please install Python 3.8+ from your package manager"
    exit 1
fi

echo "✅ Python detected"
echo

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "🔧 Activating virtual environment..."
    source venv/bin/activate
else
    echo "💡 No virtual environment found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual environment created"
fi
echo

# Check and install dependencies
echo "🔍 Checking dependencies..."
python -m bot.dependency_manager
if [ $? -ne 0 ]; then
    echo
    echo "⚠️ Dependency issues detected. Installing all requirements..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install requirements"
        exit 1
    fi
    echo "✅ All dependencies installed"
fi
echo

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️ No .env file found!"
    echo "   Please create .env file with your bot tokens."
    echo "   See .env.example or README.md for setup instructions."
    exit 1
fi

echo "✅ Configuration file found"
echo

# Start the bot
echo "🚀 Starting Mean Gene Bot..."
echo "   Press Ctrl+C to stop the bot"
echo
python -m bot.main

echo
echo "🔄 Bot stopped."