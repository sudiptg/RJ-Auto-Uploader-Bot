#!/bin/bash
set -e

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q

mkdir -p downloads thumbnails database workers backups sessions
echo "🚀 Starting FlyTon Anime Pro Bot..."
python3 bot.py
