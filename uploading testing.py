pip3 install pyrogram tgcrypto --break-system-packages && python3 << 'EOF'
import os, time, asyncio, sys
from pyrogram import Client

API_ID = 23200475
API_HASH = "644e1d9e8028a5295d6979bb3a36b23b"
BOT_TOKEN = "8697464413:AAE0xNK4OFrBzzT376sUAcbJI6Y1Ys80y48"
GROUP_ID = -1003619067047

def format_size(b):
    return f"{b/(1024*1024):.2f} MB" if b >= 1024*1024 else f"{b/1024:.2f} KB"

def format_time(s):
    m, s = divmod(int(s), 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"

start_time = None

async def progress(current, total):
    global start_time
    if start_time is None:
        start_time = time.time()
    
    elapsed = time.time() - start_time
    if elapsed > 0:
        speed = current / elapsed
        percent = (current / total) * 100
        eta = (total - current) / speed if speed > 0 else 0
        
        bar_len = 30
        filled = int(bar_len * current // total)
        bar = '█' * filled + '░' * (bar_len - filled)
        
        sys.stdout.write(f'\r📤 [{bar}] {percent:.1f}%\n')
        sys.stdout.write(f'📊 {format_size(current)} / {format_size(total)}\n')
        sys.stdout.write(f'⚡ Speed: {format_size(speed)}/s\n')
        sys.stdout.write(f'⏱️  Elapsed: {format_time(elapsed)} | ETA: {format_time(eta)}\n')
        sys.stdout.write('\033[4A')  # Move cursor up
        sys.stdout.flush()

async def main():
    print("📁 Creating 100 MB test file...\n")
    with open("test.bin", 'wb') as f:
        f.write(os.urandom(100 * 1024 * 1024))
    print("✅ File created!\n")
    
    app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    
    async with app:
        print("🚀 Starting upload to Telegram...\n\n\n\n")
        global start_time
        start_time = time.time()
        
        await app.send_document(
            GROUP_ID, 
            "test.bin",
            progress=progress
        )
        
        end = time.time()
        total_time = end - start_time
        speed = 100 / total_time
        
        print('\n\n')
        result = (
            f"✅ Upload Complete!\n\n"
            f"📁 Size: 100 MB\n"
            f"⏱️  Time: {format_time(total_time)}\n"
            f"⚡ Speed: {speed:.2f} MB/s\n"
            f"🖥️  Server: Ubuntu VPS"
        )
        
        print("="*40)
        print(result)
        print("="*40)
        
        await app.send_message(GROUP_ID, result)
    
    os.remove("test.bin")
    print("\n🗑️  Test file deleted!\n")

asyncio.run(main())
EOF