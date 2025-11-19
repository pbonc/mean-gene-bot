@echo off
title Mean Gene Bot Startup

echo ========================================
echo    🤖 Mean Gene Bot Startup Script
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed or not in PATH
    echo    Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo ✅ Python detected
echo.

REM Check if virtual environment exists
if exist "venv" (
    echo 🔧 Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo 💡 No virtual environment found. Creating one...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo ✅ Virtual environment created
)
echo.

REM Check and install dependencies
echo 🔍 Checking dependencies...
python -m bot.dependency_manager
if %errorlevel% neq 0 (
    echo.
    echo ⚠️ Dependency issues detected. Installing all requirements...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ❌ Failed to install requirements
        pause
        exit /b 1
    )
    echo ✅ All dependencies installed
)
echo.

REM Check for .env file
if not exist ".env" (
    echo ⚠️ No .env file found!
    echo    Please create .env file with your bot tokens.
    echo    See .env.example or README.md for setup instructions.
    pause
    exit /b 1
)

echo ✅ Configuration file found
echo.

REM Start the bot
echo 🚀 Starting Mean Gene Bot...
echo    Press Ctrl+C to stop the bot
echo.
python -m bot.main

REM Handle exit
echo.
echo 🔄 Bot stopped. Press any key to exit...
pause >nul