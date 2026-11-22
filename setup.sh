#!/bin/bash
set -e

echo "📦 Updating system packages..."
sudo apt update -qq && sudo apt upgrade -y -qq

echo "📦 Installing Python, FFmpeg, and Aria2..."
sudo apt install -y -qq wget curl unzip gnupg2 software-properties-common python3 python3-pip python3-venv ffmpeg aria2

echo "📦 Checking Google Chrome..."
if ! command -v google-chrome &> /dev/null; then
    wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt install -y -qq /tmp/chrome.deb
    rm -f /tmp/chrome.deb
    echo "✅ Google Chrome installed."
else
    echo "✅ Google Chrome already installed."
fi

echo "📦 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📦 Installing Python requirements..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

mkdir -p downloads thumbnails database workers backups sessions
echo "🎉 VPS Setup Complete! Now create .env and run ./start.sh"
