@echo off
echo ==============================================================
echo ClipPods Environment Setup (Windows)
echo ==============================================================
echo.

set TOOLS_DIR=D:\tools

if not exist "%TOOLS_DIR%" (
    echo Creating missing tools directory at %TOOLS_DIR%...
    mkdir "%TOOLS_DIR%"
)

echo Checking for Node.js...
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Node.js is NOT installed or not in PATH!
    echo Please install Node.js 18+ manually or via NVM.
    echo Recommended: Install in D:\tools\nodejs and add to PATH.
) else (
    echo [OK] Node.js is installed.
)

echo.
echo Checking for FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg is NOT installed or not in PATH!
    echo Please download FFmpeg and extract it to D:\tools\ffmpeg.
    echo Ensure D:\tools\ffmpeg\bin is in your system PATH.
) else (
    echo [OK] FFmpeg is installed.
)

echo.
echo Checking for yt-dlp...
yt-dlp --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] yt-dlp is NOT installed or not in PATH!
    echo Please download yt-dlp.exe to D:\tools\yt-dlp.
    echo Ensure D:\tools\yt-dlp is in your system PATH.
) else (
    echo [OK] yt-dlp is installed.
)

echo.
echo Checking for Docker...
docker -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Docker is NOT installed or not in PATH!
    echo You need Docker Desktop to run the Redis container.
) else (
    echo [OK] Docker is installed.
)

echo.
echo Please review any warnings above. Follow instructions before running the application.
pause
