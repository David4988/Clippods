Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "ClipPods Environment Setup (Windows PowerShell)" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

$toolsDir = "D:\tools"

if (-Not (Test-Path -Path $toolsDir)) {
    Write-Host "Creating missing tools directory at $toolsDir..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $toolsDir | Out-Null
}

Write-Host "Checking for Node.js..."
try {
    $nodeVer = node -v
    Write-Host "[OK] Node.js is installed: $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Node.js is NOT installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please install Node.js 18+ manually or via NVM."
    Write-Host "Recommended: Install in $toolsDir\nodejs and add to PATH."
}

Write-Host "`nChecking for FFmpeg..."
try {
    $ffmpegVer = ffmpeg -version
    Write-Host "[OK] FFmpeg is installed." -ForegroundColor Green
} catch {
    Write-Host "[WARNING] FFmpeg is NOT installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please download FFmpeg and extract it to $toolsDir\ffmpeg."
    Write-Host "Ensure $toolsDir\ffmpeg\bin is in your system PATH."
}

Write-Host "`nChecking for yt-dlp..."
try {
    $ytdlpVer = yt-dlp --version
    Write-Host "[OK] yt-dlp is installed." -ForegroundColor Green
} catch {
    Write-Host "[WARNING] yt-dlp is NOT installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please download yt-dlp.exe to $toolsDir\yt-dlp."
    Write-Host "Ensure $toolsDir\yt-dlp is in your system PATH."
}

Write-Host "`nChecking for Docker..."
try {
    $dockerVer = docker -v
    Write-Host "[OK] Docker is installed." -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Docker is NOT installed or not in PATH!" -ForegroundColor Red
    Write-Host "You need Docker Desktop to run the Redis container."
}

Write-Host "`nPlease review any warnings above. Follow instructions before running the application." -ForegroundColor Cyan
