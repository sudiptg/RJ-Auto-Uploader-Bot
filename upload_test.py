import os
import sys
import time
import asyncio
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.enums import ParseMode

load_dotenv()

IS_RENDER = bool(os.environ.get("RENDER")) or bool(os.environ.get("RENDER_EXTERNAL_URL"))
SERVER_LABEL = "Render Cloud" if IS_RENDER else "Ubuntu VPS"

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TEST_CHAT_ID = int(os.environ.get("BACKUP_CHANNEL") or os.environ.get("OWNER_ID") or "0")

# Render par low RAM ki wajah se 25 MB, VPS par 100 MB (ya command se custom MB de sakte ho)
DEFAULT_SIZE_MB = 25 if IS_RENDER else 100
if len(sys.argv) > 1 and sys.argv[1].isdigit():
    TEST_SIZE_MB = max(1, min(int(sys.argv[1]), 1500))
else:
    TEST_SIZE_MB = DEFAULT_SIZE_MB


def format_size(b: float) -> str:
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):.2f} MB"
    return f"{b / 1024:.2f} KB"


def format_time(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s" if m > 0 else f"{sec}s"


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

        bar_len = 25
        filled = int(bar_len * current // total)
        bar = "█" * filled + "░" * (bar_len - filled)

        sys.stdout.write(
            f"\r📤 [{bar}] {percent:.1f}% | {format_size(current)}/{format_size(total)} | "
            f"⚡ {format_size(speed)}/s | ETA: {format_time(eta)}   "
        )
        sys.stdout.flush()


async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN or not TEST_CHAT_ID:
        print("❌ Missing API_ID, API_HASH, BOT_TOKEN, or OWNER_ID/BACKUP_CHANNEL in .env / Environment!")
        return

    test_file = f"speed_test_{TEST_SIZE_MB}mb.bin"
    print(f"📁 Creating {TEST_SIZE_MB} MB test file ({SERVER_LABEL})...")

    # 1 MB chunks mein write karne se Render par RAM spike nahi aata
    with open(test_file, "wb") as f:
        for _ in range(TEST_SIZE_MB):
            f.write(os.urandom(1024 * 1024))
    print("✅ Test file ready!")

    os.makedirs("sessions", exist_ok=True)
    app = Client(
        "speedtest_session",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workdir="sessions",
        in_memory=IS_RENDER,
    )

    try:
        async with app:
            print(f"🚀 Uploading {TEST_SIZE_MB} MB to Telegram ({TEST_CHAT_ID})...")
            global start_time
            start_time = time.time()

            await app.send_document(
                chat_id=TEST_CHAT_ID,
                document=test_file,
                caption=f"🧪 <b>Speed Test File ({TEST_SIZE_MB} MB)</b>",
                parse_mode=ParseMode.HTML,
                progress=progress,
            )

            total_time = max(0.1, time.time() - start_time)
            speed = TEST_SIZE_MB / total_time

            result = (
                f"<blockquote>✅ <b>UPLOAD SPEED TEST COMPLETE</b></blockquote>\n"
                f"<blockquote>"
                f"╭ 📁 <b>Size:</b> <code>{TEST_SIZE_MB} MB</code>\n"
                f"├ ⏱ <b>Time:</b> <code>{format_time(total_time)}</code>\n"
                f"├ ⚡ <b>Speed:</b> <code>{speed:.2f} MB/s</code>\n"
                f"╰ 🖥 <b>Server:</b> <code>{SERVER_LABEL}</code>"
                f"</blockquote>"
            )

            print(f"\n\n✅ Upload Complete! Speed: {speed:.2f} MB/s | Time: {format_time(total_time)}")
            await app.send_message(TEST_CHAT_ID, result, parse_mode=ParseMode.HTML)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
            print("🗑️ Test file deleted!")


if __name__ == "__main__":
    asyncio.run(main())
