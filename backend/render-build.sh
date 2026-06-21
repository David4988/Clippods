#!/usr/bin/env bash
# exit on error
set -o errexit
set -o pipefail

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Creating local bin directory..."
mkdir -p ./bin

echo "Downloading static ffmpeg binary..."
wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

echo "Extracting binaries..."
tar -xf ffmpeg-release-amd64-static.tar.xz

echo "Moving ffmpeg and ffprobe to ./bin..."
cp ffmpeg-*-static/ffmpeg ./bin/
cp ffmpeg-*-static/ffprobe ./bin/

chmod +x ./bin/ffmpeg
chmod +x ./bin/ffprobe

echo "Cleaning up temporary files..."
rm -rf ffmpeg-release-amd64-static.tar.xz ffmpeg-*-static

echo "Build complete. Binaries located at ./bin"
