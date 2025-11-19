@echo off
title Playlist Importer - Mean Gene Bot

echo ========================================
echo    🎵 Playlist Importer Tool
echo ========================================
echo.

REM Change to the project directory
cd /d "%~dp0.."

REM Run the playlist importer
python tools\playlist_importer.py

echo.
echo Press any key to exit...
pause >nul