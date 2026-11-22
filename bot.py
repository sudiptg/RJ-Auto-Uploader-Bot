# =============================================================================
# ⚡ FLYTON ANIME PRO BOT — UNIFIED RENDER + VPS EDITION (FULL UPDATED CODE)
# =============================================================================
import os
import re
import html
import json
import time
import uuid
import pickle
import shutil
import zipfile
import asyncio
import warnings
import traceback
import subprocess
import urllib.parse
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher

import psutil
import aiohttp
from aiohttp import web
import nest_asyncio
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Python 3.12 / 3.14 Event Loop Fix for Pyrogram
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand

warnings.filterwarnings("ignore")
nest_asyncio.apply()
load_dotenv()

# =============================================================================
# 1. AUTO ENVIRONMENT DETECTION (RENDER VS VPS)
# =============================================================================
IS_RENDER = bool(os.environ.get("RENDER")) or bool(os.environ.get("RENDER_EXTERNAL_URL"))
RUN_MODE = "Render Cloud (Low-RAM Safe)" if IS_RENDER else "Ubuntu VPS (High Performance)"

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
BACKUP_CHANNEL = int(os.environ.get("BACKUP_CHANNEL", "0"))

BRAND_NAME = os.environ.get("BRAND_NAME", "FlyTon Anime")
BRAND_USERNAME = os.environ.get("BRAND_USERNAME", "@FlyTon_Anime")
BRAND_URL = os.environ.get("BRAND_URL", "https://t.me/FlyTon_Anime")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
THUMB_DIR = os.path.join(BASE_DIR, "thumbnails")
DB_DIR = os.path.join(BASE_DIR, "database")
WORKER_DIR = os.path.join(BASE_DIR, "workers")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
SESSION_DIR = os.path.join(BASE_DIR, "sessions")

for _d in [DOWNLOAD_DIR, THUMB_DIR, DB_DIR, WORKER_DIR, BACKUP_DIR, SESSION_DIR]:
    os.makedirs(_d, exist_ok=True)

DB_FILE = os.path.join(DB_DIR, "main_db.pkl")

# Smart Default Limits: 1 worker on Render (512MB RAM), 4 workers on VPS
MAX_BATCH = 15
MAX_QUEUE = 100
MAX_DOWNLOAD_WORKERS = int(os.environ.get("MAX_DOWNLOAD_WORKERS", "1" if IS_RENDER else "4"))
MAX_UPLOAD_PARALLEL = int(os.environ.get("MAX_UPLOAD_PARALLEL", "1" if IS_RENDER else "4"))
MAX_BATCH_WORKERS = int(os.environ.get("MAX_BATCH_WORKERS", "1" if IS_RENDER else "2"))

MAX_FILE_SIZE = 1.9 * 1024 * 1024 * 1024
PROGRESS_UPDATE_INTERVAL = 5
MONITOR_NEW_EP_DELAY = 180

DEFAULT_WEBSITES = {
    "toono": {
        "patterns": ["toono.in", "toono.app", "toono.me"],
        "name": "🎌 Toono",
        "type": "codedew",
    },
    "rareanimes": {
        "patterns": [
            "rareanimes.foo",
            "rareanimes.app",
            "rareanimes.me",
            "raretoonsindia.me",
            "raretoonsindia.in",
            "raretoonsindia.com",
        ],
        "name": "🎭 RareAnimes",
        "type": "rareanimes",
    },
    "animedubhindi": {
        "patterns": ["animedubhindi.me", "animedubhindi.in", "links.animedubhindi"],
        "name": "🎬 AnimeDubHindi",
        "type": "gdflix",
    },
    "gdflix": {
        "patterns": ["gdflix.dev", "gdflix.app", "gdflix.cfd"],
        "name": "📦 GDFlix",
        "type": "gdflix_direct",
    },
    "swift": {
        "patterns": ["swift.multiquality", "multiquality.click", "liptron"],
        "name": "⚡ Swift Player",
        "type": "swift_direct",
    },
    "codedew": {
        "patterns": ["codedew.com"],
        "name": "🔗 Codedew",
        "type": "codedew_direct",
    },
}

GDFLIX_INTERMEDIATE_PATTERNS = [
    r"gdflix\.(app|dev|cfd)/zfile",
    r"instant\.busycdn\.xyz",
]

GDFLIX_FINAL_PATTERNS = [
    r"aws-eu\.online",
    r"awscdn\.rest",
    r"video-downloads\.googleusercontent\.com",
    r"\.workers\.dev/[a-f0-9]{40,}",
    r"pub-[a-f0-9]+\.r2\.dev",
]

# =============================================================================
# 2. DATABASE & PRIVATE ACCESS CONTROL
# =============================================================================
db = {
    "owner_id": OWNER_ID,
    "admins": set(),
    "monitored": {},
    "thumbnails": {},
    "captions": {},
    "rename_rules": {},
    "metadata": {},
    "channels": {},
    "websites": json.loads(json.dumps(DEFAULT_WEBSITES)),
    "settings": {"default_interval": 3},
}

task_queue = deque(maxlen=MAX_QUEUE)
active_downloads = {}
worker_status = {}
download_semaphore = None
upload_semaphore = None
batch_semaphore = None
queue_lock = None
_shutdown = False


def load_db():
    global db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "rb") as f:
                loaded = pickle.load(f)
                db.update(loaded)
        except Exception as e:
            print(f"[DB Load Warning] {e}")

    db["owner_id"] = OWNER_ID
    if isinstance(db.get("admins"), list):
        db["admins"] = set(db["admins"])
    if "websites" not in db or not db["websites"]:
        db["websites"] = json.loads(json.dumps(DEFAULT_WEBSITES))
    for key in ["monitored", "thumbnails", "captions", "rename_rules", "metadata", "channels"]:
        if key not in db:
            db[key] = {}


def save_db():
    try:
        with open(DB_FILE, "wb") as f:
            pickle.dump(db, f)
    except Exception as e:
        print(f"[DB Save Warning] {e}")


def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


def is_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in db.get("admins", set())


def is_authorized(uid: int) -> bool:
    return is_admin(uid)


def role_badge(uid: int) -> str:
    if is_owner(uid):
        return "👑 Owner"
    if uid in db.get("admins", set()):
        return "⚔️ Admin Friend"
    return "🔒 Unauthorized"


def _esc(val) -> str:
    return html.escape(str(val if val is not None else ""))


# =============================================================================
# 3. RENDER WEB HEALTH SERVER (RUNS AUTOMATICALLY ON RENDER OR WHEN PORT IS SET)
# =============================================================================
async def start_web_server():
    app = web.Application()

    async def handle_root(request):
        return web.Response(
            text=f"⚡ {BRAND_NAME} Bot is Online | Mode: {RUN_MODE} | Queue: {len(task_queue)}"
        )

    async def handle_health(request):
        return web.json_response({
            "status": "ok",
            "brand": BRAND_NAME,
            "mode": RUN_MODE,
            "workers": MAX_DOWNLOAD_WORKERS,
            "queue": len(task_queue),
            "active": len(active_downloads),
        })

    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web Server Bound on 0.0.0.0:{port} ({RUN_MODE})")
    return runner


# =============================================================================
# 4. COLORFUL BUTTON ENGINE (BLUE / GREEN / RED WITH SAFE FALLBACK)
# =============================================================================
async def tg_api_request(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=15) as resp:
                return await resp.json()
    except Exception as e:
        print(f"[BotAPI Warning] {method}: {e}")
        return {"ok": False, "description": str(e)}


def _strip_styles(rows: list) -> list:
    return [[{k: v for k, v in btn.items() if k != "style"} for btn in row] for row in rows]


async def send_colored_msg(chat_id: int, text: str, buttons: list = None, reply_to: int = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    res = await tg_api_request("sendMessage", payload)
    if not res.get("ok") and buttons:
        payload["reply_markup"] = {"inline_keyboard": _strip_styles(buttons)}
        res = await tg_api_request("sendMessage", payload)
    return res


async def edit_colored_msg(chat_id: int, message_id: int, text: str, buttons: list = None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    res = await tg_api_request("editMessageText", payload)
    if not res.get("ok") and buttons:
        if "message is not modified" in (res.get("description") or "").lower():
            return res
        payload["reply_markup"] = {"inline_keyboard": _strip_styles(buttons)}
        res = await tg_api_request("editMessageText", payload)
    return res


async def deny_unauthorized(m):
    await send_colored_msg(
        m.chat.id,
        f"<blockquote>🔒 <b>PRIVATE BOT ACCESS DENIED</b></blockquote>\n"
        f"<blockquote>यह बॉट सिर्फ <b>{_esc(BRAND_NAME)}</b> के Owner और authorized Admin दोस्तों के लिए है।</blockquote>",
        buttons=[[{"text": f"📢 Join {BRAND_NAME}", "url": BRAND_URL, "style": "primary"}]],
        reply_to=m.id,
    )


# =============================================================================
# 5. DYNAMIC WEBSITE & DOMAIN DETECTOR
# =============================================================================
def detect_website(url: str):
    url_lower = url.lower()
    websites = db.get("websites", DEFAULT_WEBSITES)

    try:
        clean_url = url_lower.replace("http://", "").replace("https://", "")
        domain_part = clean_url.split("/")[0].replace("www.", "")
        base_name = domain_part.split(".")[0]
    except Exception:
        domain_part, base_name = url_lower, url_lower

    for site_key, site_data in websites.items():
        for pattern in site_data.get("patterns", []):
            p_low = pattern.lower().strip()
            if p_low in url_lower or domain_part == p_low:
                return site_key, site_data

    for site_key, site_data in websites.items():
        for pattern in site_data.get("patterns", []):
            p_base = pattern.lower().split(".")[0]
            if len(p_base) >= 4 and (p_base in base_name or base_name in p_base):
                return site_key, site_data

    best_match, best_score = None, 0.0
    for site_key, site_data in websites.items():
        for pattern in site_data.get("patterns", []):
            p_base = pattern.lower().split(".")[0]
            score = SequenceMatcher(None, base_name, p_base).ratio()
            if score > best_score:
                best_score = score
                best_match = (site_key, site_data)

    return best_match if best_score >= 0.72 else (None, None)


# =============================================================================
# 6. MEDIA, AUDIO FILTER, METADATA & FORMATTING HELPERS
# =============================================================================
def fmt_bytes(s: float) -> str:
    if s < 1024:
        return f"{int(s)} B"
    if s < 1024**2:
        return f"{s / 1024:.2f} KB"
    if s < 1024**3:
        return f"{s / (1024**2):.2f} MB"
    return f"{s / (1024**3):.2f} GB"


def fmt_time(s: float) -> str:
    if s < 0 or s > 86400:
        return "∞"
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s // 60)}m {int(s % 60)}s"
    return f"{int(s // 3600)}h {int((s % 3600) // 60)}m"


def fmt_dur(s: int) -> str:
    if s <= 0:
        return "00:00"
    h, m, sec = int(s // 3600), int((s % 3600) // 60), int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def progress_bar(p: float, length: int = 14) -> str:
    filled = max(0, min(length, int(length * p / 100)))
    return f"[{'█' * filled}{'░' * (length - filled)}]"


def clean_unwanted_tags(filename: str, user_id: int = None) -> str:
    result = filename
    for pat in [
        r"\[RTI\]", r"\[RareToonsIndia\]", r"RareToonsIndia", r"\[Toono\]",
        r"Toono\.in", r"Toono\.app", r"Toono", r"\[HindiDub\]", r"\[RAI\]",
    ]:
        result = re.sub(pat, "", result, flags=re.IGNORECASE)
    if user_id and user_id in db.get("rename_rules", {}):
        for rule in db["rename_rules"][user_id]:
            result = re.sub(re.escape(rule), "", result, flags=re.IGNORECASE)
    result = re.sub(r"[\s_]+", " ", result)
    result = re.sub(r"\[\s*\]", "", result)
    return result.strip(" _-.")


def clean_anime_name(filename: str) -> str:
    name = re.sub(r"\.(mp4|mkv|avi|webm|zip)$", "", str(filename), flags=re.I)
    name = re.sub(r"^meta_\d+_", "", name)
    name = re.sub(r"\[.*?\]", "", name)
    for pat in [
        r"\s*S\d+\s*E\d+", r"\s*Season\s*\d+", r"\s*Episode\s*\d+",
        r"\s+\d+x\d+", r"\s+\d{3,4}[pP]", r"\s+(x264|x265|HEVC|WEB|BluRay|HDRip)",
        r"\s+(Hindi|English|Tamil|Telugu|Japanese|Multi|Dual|Dubbed)",
    ]:
        m = re.search(pat, name, re.I)
        if m:
            name = name[:m.start()]
    name = re.sub(r"[\s_\-]+", " ", name).strip(" _-.,")
    return name if len(name) > 1 else "Anime"


def extract_season_episode(filename: str):
    m = re.search(r"S(\d+)\s*E(\d+)", filename, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    s_m = re.search(r"Season\s*(\d+)", filename, re.I)
    e_m = re.search(r"(?:Episode|Ep|E)\s*0?(\d+)", filename, re.I)
    return (int(s_m.group(1)) if s_m else None), (int(e_m.group(1)) if e_m else None)


def video_info(path: str):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        d = json.loads(r.stdout)
        dur = int(float(d.get("format", {}).get("duration", 0)))
        w, h = 1280, 720
        for s in d.get("streams", []):
            if s.get("codec_type") == "video":
                w, h = s.get("width", 1280), s.get("height", 720)
                break
        return dur, w, h
    except Exception:
        return 0, 1280, 720


def get_real_quality(path: str) -> str:
    _, _, h = video_info(path)
    if h >= 1080:
        return "1080P FHD"
    if h >= 720:
        return "720P HD"
    if h >= 480:
        return "480P SD"
    if h >= 360:
        return "360P SD"
    return f"{h}P" if h else "HD"


def get_audio_languages(path: str) -> str:
    iso_map = {
        "hin": "Hindi", "hi": "Hindi", "hindi": "Hindi",
        "eng": "English", "en": "English", "english": "English",
        "jpn": "Japanese", "ja": "Japanese", "japanese": "Japanese",
        "tam": "Tamil", "ta": "Tamil", "tamil": "Tamil",
        "tel": "Telugu", "te": "Telugu", "telugu": "Telugu",
        "kor": "Korean", "ko": "Korean", "ben": "Bengali",
    }
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, text=True, timeout=25,
        )
        data = json.loads(r.stdout)
        langs = []
        for s in data.get("streams", []):
            if s.get("codec_type") == "audio":
                tags = s.get("tags", {})
                code = (tags.get("language") or tags.get("LANGUAGE") or "").lower().strip()
                title = (tags.get("title") or tags.get("TITLE") or "").lower().strip()
                found = iso_map.get(code)
                if not found:
                    for _, v in iso_map.items():
                        if re.search(r"\b" + re.escape(v) + r"\b", title, re.I):
                            found = v
                            break
                if found and found not in langs:
                    langs.append(found)
        if langs:
            return ", ".join(langs)
    except Exception:
        pass
    fname = os.path.basename(path).lower()
    return "Hindi" if "hindi" in fname else ("Dual Audio" if "dual" in fname else "Multi Audio")


def make_thumb(video_path: str, out_path: str):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, "-vframes", "1", "-vf", "scale=320:-1", "-q:v", "2", out_path],
            capture_output=True, timeout=30,
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
    except Exception:
        pass
    return None


def ensure_mp4_extension(filepath: str) -> str:
    if not os.path.exists(filepath) or filepath.lower().endswith(".mp4"):
        return filepath
    base, _ = os.path.splitext(filepath)
    new_path = base + ".mp4"
    try:
        os.rename(filepath, new_path)
        return new_path
    except Exception:
        return filepath


def validate_video_file(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 10240 and path.lower().endswith(
        (".mp4", ".mkv", ".avi", ".webm", ".mov")
    )


async def filter_audio_tracks(input_path: str, languages: str, output_dir: str) -> str:
    if not languages or languages.lower() == "all":
        return input_path
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_path],
            capture_output=True, text=True, timeout=30,
        )
        audio_tracks = [s for s in json.loads(r.stdout).get("streams", []) if s.get("codec_type") == "audio"]
        if len(audio_tracks) <= 1:
            return input_path

        lang_to_iso = {
            "hindi": "hin", "hin": "hin", "english": "eng", "eng": "eng",
            "tamil": "tam", "tam": "tam", "telugu": "tel", "tel": "tel",
            "japanese": "jpn", "jpn": "jpn", "korean": "kor", "kor": "kor",
        }
        req_iso = {lang_to_iso.get(x.strip().lower(), x.strip().lower()) for x in languages.replace("+", ",").split(",")}
        keep = [t["index"] for t in audio_tracks if (t.get("tags", {}).get("language") or "").lower().strip() in req_iso]
        if not keep or len(keep) >= len(audio_tracks):
            return input_path

        out_path = os.path.join(output_dir, f"af_{int(time.time())}_{os.path.basename(input_path)}")
        cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:v:0"]
        for idx in keep:
            cmd.extend(["-map", f"0:{idx}"])
        cmd.extend(["-map", "0:s?", "-c", "copy", out_path])

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1024 * 1024:
            return out_path
    except Exception as e:
        print(f"[Audio Filter Warning] {e}")
    return input_path


async def split_large_video(input_path: str, output_dir: str) -> list:
    file_size = os.path.getsize(input_path)
    if file_size <= MAX_FILE_SIZE:
        return [input_path]
    dur, _, _ = video_info(input_path)
    if dur <= 0:
        return [input_path]

    parts_count = int(file_size / MAX_FILE_SIZE) + 1
    part_dur = dur / parts_count
    base, ext = os.path.splitext(os.path.basename(input_path))
    parts = []
    for i in range(parts_count):
        out_file = os.path.join(output_dir, f"{base}_Part{i + 1:02d}{ext or '.mp4'}")
        cmd = [
            "ffmpeg", "-y", "-ss", str(int(i * part_dur)), "-i", input_path,
            "-t", str(int(part_dur) + 2), "-c", "copy", "-avoid_negative_ts", "make_zero", out_file,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()
        if os.path.exists(out_file) and os.path.getsize(out_file) > 10240:
            parts.append(out_file)
    return parts or [input_path]


async def apply_metadata_tag(input_path: str, tag: str, title: str) -> str:
    out_path = os.path.join(os.path.dirname(input_path), f"meta_{int(time.time())}_{os.path.basename(input_path)}")
    cmd = [
        "ffmpeg", "-y", "-i", input_path, "-map", "0", "-c", "copy",
        "-metadata", f"title=[{tag}] {title}",
        "-metadata", f"artist={tag}",
        "-metadata", f"comment={tag}",
        "-metadata", f"encoder={tag}",
        out_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.wait(), timeout=240)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10240:
            return out_path
    except Exception:
        pass
    return input_path


def build_caption(anime_name: str, filepath: str, size: int, duration: int, user_id: int) -> str:
    raw = os.path.basename(filepath)
    clean_file = clean_unwanted_tags(raw, user_id)
    display_name = clean_anime_name(clean_file) or anime_name
    season, episode = extract_season_episode(raw)
    quality = get_real_quality(filepath)
    language = get_audio_languages(filepath)
    sz_str, dur_str = fmt_bytes(size), fmt_dur(duration)

    if user_id in db.get("captions", {}):
        tpl = db["captions"][user_id]
        for k, v in {
            "{f}": _esc(display_name), "{s}": str(season or "01"), "{e}": str(episode or "01"),
            "{q}": _esc(quality), "{l}": _esc(language), "{sz}": _esc(sz_str), "{d}": _esc(dur_str),
        }.items():
            tpl = re.sub(re.escape(k), v, tpl, flags=re.I)
        return tpl

    return (
        f"<blockquote>🎬 <b>{_esc(display_name)}</b></blockquote>\n"
        f"<blockquote>"
        f"╭ 🏝️ <b>Season:</b> <code>{season or 'N/A'}</code>\n"
        f"├ 📺 <b>Episode:</b> <code>{episode or 'N/A'}</code>\n"
        f"├ 🌐 <b>Audio:</b> <code>{_esc(language)}</code>\n"
        f"├ 📊 <b>Quality:</b> <code>{_esc(quality)}</code>\n"
        f"├ 📦 <b>Size:</b> <code>{_esc(sz_str)}</code>\n"
        f"╰ ⏱️ <b>Duration:</b> <code>{_esc(dur_str)}</code>"
        f"</blockquote>\n"
        f"<blockquote>⚡ <b>{_esc(BRAND_NAME)}</b> • {_esc(BRAND_USERNAME)}</blockquote>"
    )


def smart_thumb_match(anime_name: str, user_thumbs: dict):
    if not user_thumbs:
        return None
    if anime_name in user_thumbs:
        return user_thumbs[anime_name]
    best, ratio = None, 0.0
    for k in user_thumbs:
        r = SequenceMatcher(None, anime_name.lower(), k.lower()).ratio()
        if r > ratio:
            best, ratio = k, r
    return user_thumbs[best] if ratio >= 0.65 else None


# =============================================================================
# 7. DUAL CHROME / CHROMIUM DRIVER (WORKS ON RENDER DOCKER & UBUNTU VPS)
# =============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--window-size=1280,720")
    if IS_RENDER:
        opts.add_argument("--blink-settings=imagesEnabled=false")
        opts.add_argument("--js-flags=--max-old-space-size=256")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    for bin_path in [
        os.environ.get("CHROME_BIN", ""),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]:
        if bin_path and os.path.exists(bin_path):
            opts.binary_location = bin_path
            break

    driver_path = None
    for drv in [
        os.environ.get("CHROMEDRIVER_PATH", ""),
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver",
    ]:
        if drv and os.path.exists(drv):
            driver_path = drv
            break

    service = Service(driver_path) if driver_path else Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


class Task:
    def __init__(self, user_id, chat_id, content_type, url):
        self.task_id = f"task_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:5]}"
        self.cancel_id = uuid.uuid4().hex[:6]
        self.user_id = user_id
        self.chat_id = chat_id
        self.content_type = content_type
        self.url = url
        self.directory = os.path.join(WORKER_DIR, self.task_id)
        self.files = []
        self.status = "pending"
        self.created_at = time.time()
        self.series_name = "Anime"
        self.season = 1
        self.episode = 1
        self.episode_data = None
        self.cancelled = False
        self.active_process = None
        self.last_error = ""
        os.makedirs(self.directory, exist_ok=True)

    def cancel(self):
        self.cancelled = True
        self.status = "cancelled"
        if self.active_process:
            try:
                self.active_process.terminate()
                self.active_process.kill()
            except Exception:
                pass
            self.active_process = None

    def cleanup(self):
        shutil.rmtree(self.directory, ignore_errors=True)


class Status:
    def __init__(self, client, chat_id, msg=None):
        self.client = client
        self.chat_id = chat_id
        self.msg = msg
        self.last_update = 0

    async def create(self, text: str):
        try:
            self.msg = await self.client.send_message(self.chat_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return self.msg

    async def update(self, text: str, force: bool = False):
        now = time.time()
        if self.msg and (force or now - self.last_update >= PROGRESS_UPDATE_INTERVAL):
            try:
                await self.msg.edit_text(text, parse_mode=ParseMode.HTML)
                self.last_update = now
            except Exception:
                pass


# =============================================================================
# 8. MULTI-WEBSITE FINDERS & NON-BLOCKING DOWNLOADERS
# =============================================================================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


async def fetch_soup(url: str):
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=20, ssl=False) as resp:
                if resp.status == 200:
                    return BeautifulSoup(await resp.text(errors="ignore"), "html.parser")
    except Exception as e:
        print(f"[Fetch Warning] {url[:50]}: {e}")
    return None


class ToonoFinder:
    async def get_info(self, url: str):
        driver = None
        try:
            driver = await asyncio.to_thread(get_driver)
            await asyncio.to_thread(driver.get, url)
            await asyncio.sleep(3)
            for _ in range(3):
                await asyncio.to_thread(driver.execute_script, "window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(0.8)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Toono Anime"

            eps, seen = [], set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/episode/" not in href.lower():
                    continue
                season, ep = 1, 0
                m = re.search(r"-(\d+)x(\d+)", href)
                if m:
                    season, ep = int(m.group(1)), int(m.group(2))
                else:
                    m2 = re.search(r"(\d+)/?$", href)
                    if m2:
                        ep = int(m2.group(1))
                if ep > 0 and (season, ep) not in seen:
                    seen.add((season, ep))
                    eps.append((season, ep, urllib.parse.urljoin(url, href)))
            if not eps:
                return title, 1, 0, []
            eps.sort(key=lambda x: (x[0], x[1]))
            return title, eps[-1][0], eps[-1][1], eps
        except Exception as e:
            print(f"[ToonoFinder Error] {e}")
            return None, 1, 0, []
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


class RareAnimesFinder:
    async def get_info(self, url: str):
        try:
            soup = await fetch_soup(url)
            if not soup:
                return None, 1, 0, []
            raw_title = soup.title.string.strip() if soup.title and soup.title.string else "RareAnimes"
            title = re.sub(r"\s*[-|].*$", "", raw_title).strip()
            s_m = re.search(r"season[- ]?(\d+)", url + " " + raw_title, re.I)
            season = int(s_m.group(1)) if s_m else 1

            content = soup.find("div", class_="entry-content") or soup.find("article") or soup
            eps, seen = [], set()
            keywords = ["watchmultiquality", "multiquality", "multquality", "codedew"]
            for a in content.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text(" ", strip=True)
                clean_txt = re.sub(r"[\s_-]+", "", txt.lower())
                if any(k in clean_txt or k in href.lower() for k in keywords) and href not in seen:
                    seen.add(href)
                    ep_m = re.search(r"(?:episode|ep|e)[\s_-]*0?(\d+)", txt, re.I)
                    ep_num = int(ep_m.group(1)) if ep_m else (len(eps) + 1)
                    eps.append((season, ep_num, href))
            if not eps:
                return title, season, 0, []
            eps.sort(key=lambda x: x[1])
            return title, season, eps[-1][1], eps
        except Exception as e:
            print(f"[RareAnimes Error] {e}")
            return None, 1, 0, []


class AnimeDubHindiFinder:
    async def get_info(self, url: str):
        try:
            soup = await fetch_soup(url)
            if not soup:
                return None, 1, 0, None, {}
            raw_title = soup.title.string.strip() if soup.title and soup.title.string else "AnimeDubHindi"
            title = re.sub(r"\s*[-|].*$", "", raw_title).strip()
            s_m = re.search(r"season\s*(\d+)", raw_title, re.I)
            season = int(s_m.group(1)) if s_m else 1

            redirect_url = None
            for a in soup.find_all("a", href=True):
                if "links.animedubhindi" in a["href"] or "gdflix" in a["href"].lower():
                    redirect_url = a["href"]
                    break
            target_page = redirect_url or url
            episodes = await self.parse_episodes(target_page)
            return title, season, (max(episodes.keys()) if episodes else 0), target_page, episodes
        except Exception as e:
            print(f"[AnimeDubHindi Error] {e}")
            return None, 1, 0, None, {}

    async def parse_episodes(self, page_url: str) -> dict:
        soup = await fetch_soup(page_url)
        if not soup:
            return {}
        episodes, current_ep = {}, 1
        for tag in soup.find_all(["p", "h2", "h3", "div", "a", "strong"]):
            txt = tag.get_text(" ", strip=True)
            if tag.name != "a" and len(txt) < 55:
                m = re.search(r"Episode\s*[:\-\s]*0?(\d+)", txt, re.I)
                if m:
                    current_ep = int(m.group(1))
            if tag.name == "a" and tag.get("href"):
                href = urllib.parse.urljoin(page_url, tag["href"])
                low = (txt + " " + href).lower()
                q = "1080P" if "1080" in low else ("720P" if "720" in low else ("480P" if "480" in low else ("360P" if "360" in low else None)))
                if "gdflix" in href.lower() and "/file/" in href:
                    episodes.setdefault(current_ep, {"qualities": {}, "multi_links": {}})
                    episodes[current_ep]["qualities"][q or "720P"] = href
                elif "re.php" in href.lower() or "links.animedubhindi" in href.lower():
                    if q:
                        episodes.setdefault(current_ep, {"qualities": {}, "multi_links": {}})
                        episodes[current_ep]["multi_links"][q] = href
        return episodes


class SmartCodedewResolver:
    async def resolve(self, initial_url: str) -> str:
        current_url, visited = initial_url, set()
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for _ in range(10):
                if "cdn/ziptron" in current_url or "multiquality" in current_url or current_url in visited:
                    break
                visited.add(current_url)
                try:
                    async with session.get(current_url, timeout=20, allow_redirects=False, ssl=False) as resp:
                        if resp.status in (301, 302, 303, 307, 308):
                            loc = resp.headers.get("Location")
                            if loc:
                                current_url = urllib.parse.urljoin(current_url, loc)
                                continue
                        soup = BeautifulSoup(await resp.text(errors="ignore"), "html.parser")
                        meta = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
                        if meta and "url=" in (meta.get("content") or "").lower():
                            nxt = meta["content"].split("url=")[-1].strip().strip("\"'")
                            current_url = urllib.parse.urljoin(current_url, nxt)
                            continue
                        btn = soup.find("a", id="mainActionBtn")
                        if btn and btn.get("href") and "javascript" not in btn["href"].lower():
                            current_url = urllib.parse.urljoin(current_url, btn["href"])
                            continue
                        found = None
                        for a in soup.find_all("a", href=True):
                            h = urllib.parse.urljoin(current_url, a["href"])
                            if "cdn/ziptron" in h or ("codedew.com" in h and h != current_url):
                                found = h
                                break
                        if found:
                            current_url = found
                        else:
                            break
                except Exception:
                    break
        return current_url


async def download_direct_aiohttp(url: str, save_dir: str, task: Task, st: Status, custom_name: str = None):
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=300, ssl=False) as resp:
                resp.raise_for_status()
                filename = custom_name
                if not filename and "content-disposition" in resp.headers:
                    m = re.findall(r"filename\*?=([^;]+)", resp.headers["content-disposition"], re.I)
                    if m:
                        filename = urllib.parse.unquote(m[0].strip().strip("\"'").split("UTF-8''")[-1])
                if not filename:
                    filename = urllib.parse.unquote(url.split("/")[-1].split("?")[0]) or f"file_{int(time.time())}.mp4"

                save_path = os.path.join(save_dir, clean_unwanted_tags(filename, task.user_id))
                total = int(resp.headers.get("content-length", 0))
                downloaded, start_t = 0, time.time()

                with open(save_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(256 * 1024):
                        if task.cancelled:
                            return None
                        f.write(chunk)
                        downloaded += len(chunk)
                        if st:
                            elapsed = max(0.1, time.time() - start_t)
                            speed = downloaded / elapsed
                            pct = (downloaded / total * 100) if total else 0
                            eta = (total - downloaded) / speed if (total and speed > 0) else 0
                            await st.update(
                                f"<blockquote>📥 <b>DOWNLOADING</b></blockquote>\n"
                                f"<blockquote>🎬 <b>{_esc(task.series_name)}</b>\n"
                                f"{progress_bar(pct)} <b>{pct:.1f}%</b>\n"
                                f"📦 <code>{fmt_bytes(downloaded)} / {fmt_bytes(total) if total else '???'}</code>\n"
                                f"⚡ <code>{fmt_bytes(speed)}/s</code> | ⏱ <code>{fmt_time(eta)}</code>\n"
                                f"❌ Cancel: <code>/cancel {task.cancel_id}</code></blockquote>"
                            )
                return save_path if os.path.exists(save_path) and os.path.getsize(save_path) > 1024 else None
    except Exception as e:
        task.last_error = f"Direct download error: {str(e)[:90]}"
        print(f"[Direct Download Error] {e}")
        return None


async def resolve_gdflix_and_download(gdflix_url: str, task: Task, st: Status):
    soup = await fetch_soup(gdflix_url)
    if not soup:
        task.last_error = "GDFlix page could not be loaded."
        return None
    links = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(gdflix_url, a["href"])
        if any(re.search(p, href) for p in GDFLIX_FINAL_PATTERNS):
            links.append(href)
        elif any(re.search(p, href) for p in GDFLIX_INTERMEDIATE_PATTERNS):
            sub_soup = await fetch_soup(href)
            if sub_soup:
                for sa in sub_soup.find_all("a", href=True):
                    sh = urllib.parse.urljoin(href, sa["href"])
                    if any(re.search(p, sh) for p in GDFLIX_FINAL_PATTERNS):
                        links.append(sh)

    for link in list(dict.fromkeys(links)):
        res = await download_direct_aiohttp(link, task.directory, task, st)
        if res and os.path.getsize(res) > 5 * 1024 * 1024:
            return res
    if not task.last_error:
        task.last_error = "No working mirror found on GDFlix."
    return None


async def download_swift_with_aria2(swift_url: str, task: Task, st: Status) -> list:
    driver, files = None, []
    task.last_error = ""
    try:
        try:
            driver = await asyncio.to_thread(get_driver)
        except Exception as drv_err:
            task.last_error = f"Chrome/Chromium missing or crashed: {str(drv_err)[:100]}"
            print(f"[Driver Error] {drv_err}")
            return []

        await asyncio.to_thread(driver.get, swift_url)
        await asyncio.sleep(7)

        # Follow codedew mainActionBtn if still on redirect page
        for _ in range(3):
            cur = driver.current_url
            if "cdn/ziptron" in cur or "multiquality" in cur:
                break
            try:
                btn = driver.find_element(By.ID, "mainActionBtn")
                href = btn.get_attribute("href") or ""
                if href.startswith("http") and "javascript" not in href.lower():
                    await asyncio.to_thread(driver.get, href)
                    await asyncio.sleep(6)
                    continue
            except Exception:
                pass
            break

        final_page_url = driver.current_url
        ua = driver.execute_script("return navigator.userAgent")
        cookies = driver.get_cookies()

        cookie_file = os.path.join(task.directory, "cookies.txt")
        cookie_header = "; ".join(f"{c.get('name')}={c.get('value')}" for c in cookies if c.get("name"))
        with open(cookie_file, "w") as cf:
            cf.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                dom = c.get("domain", "")
                if not dom.startswith("."):
                    dom = "." + dom
                cf.write(
                    f"{dom}\tTRUE\t{c.get('path', '/')}\t"
                    f"{'TRUE' if c.get('secure') else 'FALSE'}\t"
                    f"{int(c.get('expiry', time.time() + 3600))}\t"
                    f"{c.get('name', '')}\t{c.get('value', '')}\n"
                )

        found = {}

        def _scan_links():
            for a in driver.find_elements(By.TAG_NAME, "a"):
                try:
                    href = a.get_attribute("href") or ""
                    txt = (a.text or "").lower() + " " + href.lower()
                    if not href.startswith("http") or "javascript" in href.lower():
                        continue
                    if any(skip in href.lower() for skip in ("rareanimes.", "raretoonsindia.", "t.me/")):
                        continue
                    for q in ["360p", "480p", "720p", "1080p"]:
                        if q[:-1] in txt and q not in found:
                            found[q] = href
                except Exception:
                    pass

        # 1. Scan main page
        _scan_links()

        # 2. Scan all iframes
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    await asyncio.sleep(1.5)
                    _scan_links()
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
        except Exception:
            pass

        driver.quit()
        driver = None

        if not found:
            task.last_error = f"Page opened ({final_page_url[:45]}...) but no 360p/480p/720p/1080p links found."
            return []

        has_aria2 = bool(shutil.which("aria2c"))
        conns = "4" if IS_RENDER else "8"

        for q in ["360p", "480p", "720p", "1080p"]:
            if q not in found or task.cancelled:
                continue

            dl_url = found[q]
            got_file = None

            # Method A: Aria2 (if installed)
            if has_aria2:
                before = set(os.listdir(task.directory))
                cmd = [
                    "aria2c", "-x", conns, "-s", conns, "-k", "1M", "-d", task.directory,
                    "--load-cookies", cookie_file, "--user-agent", ua, "--referer", final_page_url,
                    "--check-certificate=false", "--console-log-level=warn", "--file-allocation=none",
                    dl_url,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                task.active_process = proc
                await proc.wait()
                task.active_process = None
                if proc.returncode == 0:
                    for fname in (set(os.listdir(task.directory)) - before):
                        if not fname.endswith(".aria2") and fname != "cookies.txt":
                            fpath = os.path.join(task.directory, fname)
                            if os.path.getsize(fpath) > 10240:
                                got_file = ensure_mp4_extension(fpath)
                                break

            # Method B: aiohttp fallback
            if not got_file:
                try:
                    dl_headers = {"User-Agent": ua, "Referer": final_page_url}
                    if cookie_header:
                        dl_headers["Cookie"] = cookie_header
                    async with aiohttp.ClientSession(headers=dl_headers) as session:
                        async with session.get(dl_url, timeout=300, ssl=False) as resp:
                            if resp.status == 200:
                                safe_title = re.sub(r"[^a-zA-Z0-9 _-]", "", task.series_name).strip() or "Anime"
                                save_path = os.path.join(task.directory, f"{safe_title}_Ep{task.episode}_{q}.mp4")
                                with open(save_path, "wb") as f:
                                    async for chunk in resp.content.iter_chunked(256 * 1024):
                                        if task.cancelled:
                                            break
                                        f.write(chunk)
                                if os.path.exists(save_path) and os.path.getsize(save_path) > 102400:
                                    got_file = save_path
                except Exception as aio_err:
                    task.last_error = f"Download fallback failed ({q}): {str(aio_err)[:80]}"

            if got_file:
                files.append(got_file)

        if not files and not task.last_error:
            task.last_error = "Links found, but server blocked download or returned empty file."

    except Exception as e:
        task.last_error = str(e)[:120]
        print(f"[Aria2 Download Error] {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    return files


# =============================================================================
# 9. PYROGRAM BOT CLIENT & UPLOADER
# =============================================================================
bot = Client(
    "flyton_pro_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=60,
    workdir=SESSION_DIR,
    in_memory=IS_RENDER,
)


async def upload_files_for_task(task: Task, st: Status):
    valid = [f for f in task.files if validate_video_file(f)]
    if not valid:
        await st.update("<blockquote>❌ <b>No valid video files found to upload.</b></blockquote>", force=True)
        return False

    uid, cid = task.user_id, task.chat_id
    for idx, fpath in enumerate(valid, 1):
        if task.cancelled:
            break
        parts = await split_large_video(fpath, task.directory)
        for p_file in parts:
            async with upload_semaphore:
                dur, w, h = video_info(p_file)
                sz = os.path.getsize(p_file)
                display_name = clean_anime_name(os.path.basename(p_file)) or task.series_name

                upload_path = p_file
                tag = db.get("metadata", {}).get(uid, {}).get("tag")
                if tag:
                    upload_path = await apply_metadata_tag(p_file, tag, display_name)

                thumb_path = None
                tid = smart_thumb_match(display_name, db.get("thumbnails", {}).get(uid, {}))
                if tid:
                    tp = os.path.join(THUMB_DIR, f"t_{uid}_{int(time.time())}.jpg")
                    try:
                        await bot.download_media(tid, file_name=tp)
                        if os.path.exists(tp):
                            thumb_path = tp
                    except Exception:
                        pass
                if not thumb_path:
                    thumb_path = make_thumb(upload_path, os.path.join(THUMB_DIR, f"auto_{task.task_id}_{idx}.jpg"))

                cap = build_caption(display_name, upload_path, sz, dur, uid)
                start_t = time.time()

                async def _prog(cur, tot):
                    elapsed = max(0.1, time.time() - start_t)
                    spd = cur / elapsed
                    pct = (cur / tot * 100) if tot else 0
                    await st.update(
                        f"<blockquote>📤 <b>UPLOADING TO DM ({idx}/{len(valid)})</b></blockquote>\n"
                        f"<blockquote>🎬 <b>{_esc(display_name)}</b>\n"
                        f"{progress_bar(pct)} <b>{pct:.1f}%</b>\n"
                        f"📦 <code>{fmt_bytes(cur)} / {fmt_bytes(tot)}</code> | ⚡ <code>{fmt_bytes(spd)}/s</code>\n"
                        f"❌ Cancel: <code>/cancel {task.cancel_id}</code></blockquote>"
                    )

                dm_msg = await bot.send_video(
                    chat_id=cid, video=upload_path, caption=cap, parse_mode=ParseMode.HTML,
                    file_name=f"{display_name}.mp4", duration=dur, width=w, height=h,
                    thumb=thumb_path, supports_streaming=True, progress=_prog,
                )

                for ch in db.get("channels", {}).get(uid, []):
                    if SequenceMatcher(None, display_name.lower(), ch["anime"].lower()).ratio() >= 0.65:
                        langs, ch_id = ch.get("languages", "All"), int(ch["channel_id"])
                        try:
                            if langs.lower() != "all":
                                filt = await filter_audio_tracks(upload_path, langs, task.directory)
                                ch_cap = build_caption(display_name, filt, os.path.getsize(filt), dur, uid)
                                await bot.send_video(
                                    chat_id=ch_id, video=filt, caption=ch_cap, parse_mode=ParseMode.HTML,
                                    thumb=thumb_path, duration=dur, width=w, height=h, supports_streaming=True,
                                )
                                if filt != upload_path and os.path.exists(filt):
                                    os.remove(filt)
                            else:
                                await dm_msg.copy(chat_id=ch_id, caption=cap, parse_mode=ParseMode.HTML)
                        except Exception as ce:
                            print(f"[Channel Upload Warning] {ch_id}: {ce}")

                for tmp in (thumb_path, upload_path if upload_path != p_file else None):
                    if tmp and os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except Exception:
                            pass

    await st.update(
        f"<blockquote>🎉 <b>UPLOAD COMPLETE</b></blockquote>\n"
        f"<blockquote>🎬 <b>{_esc(task.series_name)}</b>\n"
        f"📁 <b>Files Delivered:</b> <code>{len(valid)}</code></blockquote>",
        force=True,
    )
    return True


async def execute_single_task(task: Task, st: Status):
    try:
        task.status = "downloading"
        task.last_error = ""
        _, site_data = detect_website(task.url)
        site_type = site_data.get("type") if site_data else "direct"
        files = []

        if site_type in ("gdflix", "gdflix_direct"):
            if "/file/" in task.url:
                f = await resolve_gdflix_and_download(task.url, task, st)
                if f:
                    files.append(ensure_mp4_extension(f))
            elif task.episode_data:
                for _, q_url in task.episode_data.get("qualities", {}).items():
                    f = await resolve_gdflix_and_download(q_url, task, st)
                    if f:
                        files.append(ensure_mp4_extension(f))
        elif site_type in ("codedew", "codedew_direct", "rareanimes", "swift_direct"):
            target_url = task.url
            if "codedew" in target_url.lower():
                target_url = await SmartCodedewResolver().resolve(target_url)
            files = await download_swift_with_aria2(target_url, task, st)
        else:
            f = await download_direct_aiohttp(task.url, task.directory, task, st)
            if f:
                files.append(ensure_mp4_extension(f) if validate_video_file(f) else f)

        if task.cancelled:
            await st.update("<blockquote>❌ <b>Task Cancelled & Cleaned!</b></blockquote>", force=True)
            return False
        if not files:
            reason = getattr(task, "last_error", "") or "No downloadable files extracted."
            await st.update(
                f"<blockquote>❌ <b>Download Failed</b></blockquote>\n"
                f"<blockquote>🔍 <b>Reason:</b> <code>{_esc(reason)}</code></blockquote>",
                force=True,
            )
            return False

        task.files = files
        task.status = "uploading"
        return await upload_files_for_task(task, st)
    except Exception as e:
        traceback.print_exc()
        await st.update(f"<blockquote>❌ <b>Error:</b> <code>{_esc(str(e)[:120])}</code></blockquote>", force=True)
        return False
    finally:
        active_downloads.pop(task.task_id, None)
        task.cleanup()


async def download_worker(wid: int):
    worker_status[wid] = "idle"
    while not _shutdown:
        item = None
        async with queue_lock:
            if task_queue:
                item = task_queue.popleft()
        if not item:
            await asyncio.sleep(1)
            continue

        task = item["task"]
        if task.cancelled:
            task.cleanup()
            continue

        sem = batch_semaphore if item["type"] == "batch" else download_semaphore
        async with sem:
            worker_status[wid] = "working"
            active_downloads[task.task_id] = task
            try:
                if item["type"] == "single":
                    await execute_single_task(task, item["status"])
                elif item["type"] == "batch":
                    for idx, (ep_num, ep_target) in enumerate(item["episodes"], 1):
                        if task.cancelled:
                            break
                        ep_task = Task(task.user_id, task.chat_id, "episode", ep_target if isinstance(ep_target, str) else task.url)
                        ep_task.series_name, ep_task.episode = task.series_name, ep_num
                        if isinstance(ep_target, dict):
                            ep_task.episode_data = ep_target
                        await item["status"].update(
                            f"<blockquote>📦 <b>BATCH PROGRESS ({idx}/{len(item['episodes'])})</b></blockquote>\n"
                            f"<blockquote>🎬 <b>{_esc(task.series_name)}</b> — Episode <code>{ep_num}</code></blockquote>",
                            force=True,
                        )
                        await execute_single_task(ep_task, item["status"])
                        await asyncio.sleep(3)
            finally:
                worker_status[wid] = "idle"
                active_downloads.pop(task.task_id, None)


async def monitor_loop():
    while not _shutdown:
        try:
            for key, data in list(db.get("monitored", {}).items()):
                if time.time() - data.get("last_check", 0) < data.get("interval", 3) * 60:
                    continue
                db["monitored"][key]["last_check"] = time.time()
                m_url = data.get("monitor_url") or data.get("series_url")
                site_key, _ = detect_website(m_url)
                last_ep, new_eps = data.get("last_episode", 0), []

                if site_key == "animedubhindi":
                    eps = await AnimeDubHindiFinder().parse_episodes(m_url)
                    new_eps = [(e, m_url, eps[e]) for e in sorted(eps.keys()) if e > last_ep]
                elif site_key == "rareanimes":
                    _, _, _, eps = await RareAnimesFinder().get_info(m_url)
                    new_eps = [(e, u, None) for _, e, u in eps if e > last_ep]
                elif site_key == "toono":
                    _, _, _, eps = await ToonoFinder().get_info(m_url)
                    new_eps = [(e, u, None) for _, e, u in eps if e > last_ep]

                if new_eps:
                    db["monitored"][key]["last_episode"] = max(x[0] for x in new_eps)
                    save_db()
                    for sub in data.get("subscribers", []):
                        await send_colored_msg(
                            sub["chat_id"],
                            f"<blockquote>🔔 <b>NEW EPISODE DETECTED</b></blockquote>\n"
                            f"<blockquote>🎬 <b>{_esc(data['series_name'])}</b>\n"
                            f"📺 Episodes: <code>{', '.join(str(x[0]) for x in new_eps)}</code></blockquote>",
                        )
                    await asyncio.sleep(MONITOR_NEW_EP_DELAY)
                    for ep_num, ep_url, ep_data in new_eps:
                        for sub in data.get("subscribers", []):
                            t = Task(sub["user_id"], sub["chat_id"], "episode", ep_url)
                            t.series_name, t.episode, t.episode_data = data["series_name"], ep_num, ep_data
                            st = Status(bot, sub["chat_id"])
                            await st.create(f"<blockquote>📥 <b>Auto-Queued Episode {ep_num}...</b></blockquote>")
                            task_queue.append({"type": "single", "task": t, "status": st})
        except Exception as e:
            print(f"[Monitor Loop Warning] {e}")
        await asyncio.sleep(45)


# =============================================================================
# 10. PRO COLORFUL UI PANEL & COMMAND HANDLERS
# =============================================================================
def build_home_panel(uid: int, first_name: str):
    working = sum(1 for s in worker_status.values() if s == "working")
    text = (
        f"<blockquote>⚡ <b>{_esc(BRAND_NAME.upper())} — PRO AUTOMATION PANEL</b> ⚡</blockquote>\n"
        f"<blockquote>"
        f"👋 <b>Welcome, {_esc(first_name)}!</b>\n"
        f"╭ 🛡 <b>Role:</b> <code>{role_badge(uid)}</code>\n"
        f"├ 🖥 <b>Server Mode:</b> <code>{_esc(RUN_MODE)}</code>\n"
        f"├ 🌐 <b>Active Sites:</b> <code>{len(db.get('websites', {}))} Platforms</code>\n"
        f"├ 📺 <b>Monitored:</b> <code>{len(db.get('monitored', {}))} Series</code>\n"
        f"├ ⚙️ <b>Workers:</b> <code>{working}/{MAX_DOWNLOAD_WORKERS}</code> | Queue: <code>{len(task_queue)}</code>\n"
        f"╰ 👥 <b>Admin Friends:</b> <code>{len(db.get('admins', set()))} Added</code>"
        f"</blockquote>\n"
        f"<blockquote>💡 <b>Tip:</b> कोई भी सपोर्टेड लिंक सीधे भेजो, ऑटो डाउनलोड चालू हो जाएगा!</blockquote>"
    )
    buttons = [
        [
            {"text": "📺 Download Guide", "callback_data": "ui_guide_dl", "style": "primary"},
            {"text": "🌐 Sites & Domains", "callback_data": "ui_sites", "style": "success"},
        ],
        [
            {"text": "📢 Channels & Media", "callback_data": "ui_guide_media", "style": "primary"},
            {"text": "📊 Live Server Stats", "callback_data": "ui_stats", "style": "success"},
        ],
    ]
    if is_owner(uid):
        buttons.append([{"text": "👑 Owner & Admin Friends", "callback_data": "ui_owner", "style": "danger"}])
    buttons.append([
        {"text": f"📢 {BRAND_NAME}", "url": BRAND_URL, "style": "primary"},
        {"text": "🔄 Refresh", "callback_data": "ui_home", "style": "success"},
    ])
    return text, buttons


@bot.on_message(filters.command("start"))
async def cmd_start(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    text, btns = build_home_panel(m.from_user.id, m.from_user.first_name)
    await send_colored_msg(m.chat.id, text, btns, reply_to=m.id)


@bot.on_message(filters.command("admin"))
async def cmd_add_admin(c, m):
    if not is_owner(m.from_user.id):
        return await send_colored_msg(m.chat.id, "<blockquote>❌ सिर्फ Owner ही Admin जोड़ सकता है!</blockquote>", reply_to=m.id)
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/admin FRIEND_USER_ID</code></blockquote>", reply_to=m.id)
    uid = int(m.command[1])
    db["admins"].add(uid)
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Admin Friend Added: <code>{uid}</code></blockquote>", reply_to=m.id)


@bot.on_message(filters.command("radmin"))
async def cmd_rem_admin(c, m):
    if not is_owner(m.from_user.id):
        return await send_colored_msg(m.chat.id, "<blockquote>❌ Owner only!</blockquote>", reply_to=m.id)
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/radmin FRIEND_USER_ID</code></blockquote>", reply_to=m.id)
    uid = int(m.command[1])
    db["admins"].discard(uid)
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>🗑 Admin Removed: <code>{uid}</code></blockquote>", reply_to=m.id)


@bot.on_message(filters.command("seeadmin"))
async def cmd_see_admin(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    admins = list(db.get("admins", set()))
    lines = "\n".join(f"• <code>{u}</code>" for u in admins) if admins else "<i>None</i>"
    await send_colored_msg(m.chat.id, f"<blockquote>👑 Owner: <code>{OWNER_ID}</code>\n⚔️ Admins:\n{lines}</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("sites"))
async def cmd_sites(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    blocks = ["<blockquote>🌐 <b>CONNECTED WEBSITES & DOMAINS</b></blockquote>"]
    for key, info in db.get("websites", {}).items():
        doms = ", ".join(f"<code>{_esc(d)}</code>" for d in info.get("patterns", []))
        blocks.append(f"<blockquote><b>{_esc(info['name'])}</b> (<code>{_esc(key)}</code> | <code>{_esc(info['type'])}</code>)\n🔗 {doms}</blockquote>")
    blocks.append(
        "<blockquote>• <code>/addsite toono toono.xyz</code>\n"
        "• <code>/domain old.in new.xyz</code>\n"
        "• <code>/delsite toono toono.in</code>\n"
        "• <code>/addcustomsite myanime myanime.pro rareanimes</code></blockquote>"
    )
    await send_colored_msg(m.chat.id, "\n".join(blocks), reply_to=m.id)


@bot.on_message(filters.command("addsite"))
async def cmd_addsite(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 3:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/addsite [site_key] [new_domain]</code></blockquote>", reply_to=m.id)
    key = m.command[1].lower().strip()
    domain = m.command[2].lower().replace("https://", "").replace("http://", "").strip("/ ")
    if key not in db["websites"]:
        return await send_colored_msg(m.chat.id, f"<blockquote>❌ Site key <code>{_esc(key)}</code> not found. Use <code>/sites</code>.</blockquote>", reply_to=m.id)
    if domain not in db["websites"][key]["patterns"]:
        db["websites"][key]["patterns"].append(domain)
        save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Added <code>{_esc(domain)}</code> to <code>{_esc(key)}</code>!</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("addcustomsite"))
async def cmd_addcustomsite(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 4:
        return await send_colored_msg(
            m.chat.id,
            "<blockquote>⚠️ Usage: <code>/addcustomsite [key] [domain] [engine]</code>\n"
            "Engines: <code>codedew</code>, <code>rareanimes</code>, <code>gdflix</code>, <code>gdflix_direct</code>, <code>swift_direct</code>, <code>direct</code></blockquote>",
            reply_to=m.id,
        )
    key = re.sub(r"[^a-z0-9_]", "", m.command[1].lower())
    domain = m.command[2].lower().replace("https://", "").replace("http://", "").strip("/ ")
    engine = m.command[3].lower().strip()
    db["websites"][key] = {"patterns": [domain], "name": f"🌐 {key.capitalize()}", "type": engine}
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Custom site <code>{_esc(key)}</code> (<code>{_esc(domain)}</code>) added!</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("delsite"))
async def cmd_delsite(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 3:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/delsite [site_key] [domain]</code></blockquote>", reply_to=m.id)
    key, domain = m.command[1].lower().strip(), m.command[2].lower().strip()
    if key in db["websites"] and domain in db["websites"][key]["patterns"]:
        db["websites"][key]["patterns"].remove(domain)
        save_db()
        return await send_colored_msg(m.chat.id, f"<blockquote>🗑 Removed <code>{_esc(domain)}</code> from <code>{_esc(key)}</code>.</blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>⚠️ Not found.</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("domain"))
async def cmd_domain_migrate(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    parts = [p for p in m.command[1:] if p.lower() != "to"]
    if len(parts) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/domain olddomain.in newdomain.xyz</code></blockquote>", reply_to=m.id)
    old_d = parts[0].lower().replace("https://", "").replace("http://", "").strip("/ ")
    new_d = parts[1].lower().replace("https://", "").replace("http://", "").strip("/ ")

    s_hits, m_hits = 0, 0
    for info in db["websites"].values():
        if old_d in info["patterns"]:
            info["patterns"] = [new_d if x == old_d else x for x in info["patterns"]]
            s_hits += 1
    for data in db["monitored"].values():
        for f in ("series_url", "monitor_url"):
            if data.get(f) and old_d in data[f]:
                data[f] = data[f].replace(old_d, new_d)
                m_hits += 1
    save_db()
    await send_colored_msg(
        m.chat.id,
        f"<blockquote>✅ <b>DOMAIN MIGRATED</b></blockquote>\n"
        f"<blockquote>🔄 <code>{_esc(old_d)}</code> ➜ <code>{_esc(new_d)}</code>\nSites: <code>{s_hits}</code> | Monitored: <code>{m_hits}</code></blockquote>",
        reply_to=m.id,
    )


@bot.on_message(filters.command("set"))
async def cmd_set(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/set [Anime_URL]</code></blockquote>", reply_to=m.id)
    url = m.command[1].strip()
    site_key, site_data = detect_website(url)
    if not site_key:
        return await send_colored_msg(m.chat.id, "<blockquote>❌ Unsupported domain! पहले <code>/addsite</code> से जोड़ो।</blockquote>", reply_to=m.id)

    st = Status(c, m.chat.id)
    await st.create(f"<blockquote>🔍 Scanning {_esc(site_data['name'])}...</blockquote>")

    title, season, latest_ep, mon_url, ep_url, ep_data = None, 1, 0, url, None, None
    if site_key == "animedubhindi":
        title, season, latest_ep, mon_url, eps = await AnimeDubHindiFinder().get_info(url)
        ep_data = eps.get(latest_ep)
    elif site_key == "rareanimes":
        title, season, latest_ep, eps = await RareAnimesFinder().get_info(url)
        ep_url = eps[-1][2] if eps else None
    elif site_key == "toono":
        title, season, latest_ep, eps = await ToonoFinder().get_info(url)
        ep_url = eps[-1][2] if eps else None

    if not title:
        return await st.update("<blockquote>❌ Could not fetch series info.</blockquote>", force=True)

    key = f"{site_key}_{re.sub(r'[^a-z0-9]', '', title.lower())}"
    db["monitored"][key] = {
        "series_name": title, "series_url": url, "monitor_url": mon_url or url,
        "site_key": site_key, "last_episode": latest_ep, "last_season": season,
        "interval": db["settings"].get("default_interval", 3), "last_check": time.time(),
        "subscribers": [{"user_id": m.from_user.id, "chat_id": m.chat.id}],
    }
    save_db()
    await st.update(
        f"<blockquote>✅ <b>MONITORING STARTED</b></blockquote>\n"
        f"<blockquote>🎬 <b>{_esc(title)}</b> | Ep <code>{latest_ep}</code> | Season <code>{season}</code></blockquote>",
        force=True,
    )
    if ep_url or ep_data:
        t = Task(m.from_user.id, m.chat.id, "episode", ep_url or url)
        t.series_name, t.episode, t.episode_data = title, latest_ep, ep_data
        task_queue.append({"type": "single", "task": t, "status": st})


@bot.on_message(filters.command("list"))
async def cmd_list(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    items = list(db.get("monitored", {}).items())
    if not items:
        return await send_colored_msg(m.chat.id, "<blockquote>📭 No monitored anime yet.</blockquote>", reply_to=m.id)
    blocks = [f"<blockquote>📺 <b>MONITORED LIST ({len(items)})</b></blockquote>"]
    for i, (_, d) in enumerate(items, 1):
        blocks.append(f"<blockquote><b>{i}. {_esc(d['series_name'])}</b> | Ep <code>{d['last_episode']}</code> (<code>{_esc(d['site_key'])}</code>)</blockquote>")
    await send_colored_msg(m.chat.id, "\n".join(blocks), reply_to=m.id)


@bot.on_message(filters.command("del"))
async def cmd_del(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    items = list(db.get("monitored", {}).items())
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/del NUMBER</code></blockquote>", reply_to=m.id)
    idx = int(m.command[1]) - 1
    if 0 <= idx < len(items):
        k, d = items[idx]
        del db["monitored"][k]
        save_db()
        return await send_colored_msg(m.chat.id, f"<blockquote>🗑 Removed <b>{_esc(d['series_name'])}</b>.</blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>❌ Invalid number.</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("batch"))
async def cmd_batch(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 3:
        return await send_colored_msg(m.chat.id, f"<blockquote>⚠️ Usage: <code>/batch URL 1-5</code> (Max {MAX_BATCH})</blockquote>", reply_to=m.id)
    url = m.command[1]
    rng = re.search(r"(\d+)\s*(?:-|to|\s)\s*(\d+)", " ".join(m.command[2:]), re.I)
    if not rng:
        return await send_colored_msg(m.chat.id, "<blockquote>❌ Invalid range. Example: <code>1-5</code></blockquote>", reply_to=m.id)
    start_ep, end_ep = sorted([int(rng.group(1)), int(rng.group(2))])
    if (end_ep - start_ep + 1) > MAX_BATCH:
        return await send_colored_msg(m.chat.id, f"<blockquote>❌ Max {MAX_BATCH} episodes allowed.</blockquote>", reply_to=m.id)

    site_key, _ = detect_website(url)
    st = Status(c, m.chat.id)
    await st.create("<blockquote>🔍 Fetching batch episodes...</blockquote>")
    title, dl_eps = "Batch Anime", []
    if site_key == "animedubhindi":
        title, _, _, _, eps = await AnimeDubHindiFinder().get_info(url)
        dl_eps = [(e, eps[e]) for e in range(start_ep, end_ep + 1) if e in eps]
    elif site_key == "rareanimes":
        title, _, _, eps = await RareAnimesFinder().get_info(url)
        dl_eps = [(e, u) for _, e, u in eps if start_ep <= e <= end_ep]
    elif site_key == "toono":
        title, _, _, eps = await ToonoFinder().get_info(url)
        dl_eps = [(e, u) for _, e, u in eps if start_ep <= e <= end_ep]

    if not dl_eps:
        return await st.update("<blockquote>❌ Requested episodes not found.</blockquote>", force=True)
    t = Task(m.from_user.id, m.chat.id, "batch", url)
    t.series_name = title or "Batch Anime"
    task_queue.append({"type": "batch", "task": t, "status": st, "episodes": dl_eps})
    await st.update(f"<blockquote>✅ Batch Queued: <b>{_esc(t.series_name)}</b> ({len(dl_eps)} eps)</blockquote>", force=True)


@bot.on_message(filters.command("l0"))
async def cmd_leech(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/l0 URL</code> or <code>/l0 URL -e [pass]</code></blockquote>", reply_to=m.id)
    url = m.command[1]
    extract = len(m.command) >= 3 and m.command[2].lower() == "-e"
    pwd = m.command[3] if (extract and len(m.command) >= 4) else None

    st = Status(c, m.chat.id)
    await st.create("<blockquote>📥 Starting Direct Leech...</blockquote>")
    t = Task(m.from_user.id, m.chat.id, "leech", url)
    t.series_name = "Direct Leech"

    fpath = await download_direct_aiohttp(url, t.directory, t, st)
    if not fpath:
        reason = t.last_error or "Leech failed."
        t.cleanup()
        return await st.update(f"<blockquote>❌ <b>Leech Failed</b>\n🔍 <code>{_esc(reason)}</code></blockquote>", force=True)

    upload_list = [fpath]
    if extract and zipfile.is_zipfile(fpath):
        ex_dir = os.path.join(t.directory, "extracted")
        os.makedirs(ex_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(fpath, "r") as zf:
                zf.extractall(ex_dir, pwd=pwd.encode() if pwd else None)
            upload_list = [os.path.join(r, fn) for r, _, fns in os.walk(ex_dir) for fn in fns if os.path.getsize(os.path.join(r, fn)) > 1024]
        except Exception as ze:
            t.cleanup()
            return await st.update(f"<blockquote>❌ ZIP Error: <code>{_esc(ze)}</code></blockquote>", force=True)

    vids = [ensure_mp4_extension(x) for x in upload_list if validate_video_file(x)]
    if vids:
        t.files = vids
        await upload_files_for_task(t, st)
    else:
        for doc in upload_list:
            await c.send_document(m.chat.id, doc, caption=f"📁 <b>{_esc(os.path.basename(doc))}</b>", parse_mode=ParseMode.HTML)
        await st.update("<blockquote>✅ Leech complete!</blockquote>", force=True)
    t.cleanup()


@bot.on_message(filters.command("addchannel"))
async def cmd_addchannel(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    text = m.text.split(None, 1)[1] if len(m.text.split(None, 1)) > 1 else ""
    ch_id = m.reply_to_message.forward_from_chat.id if (m.reply_to_message and m.reply_to_message.forward_from_chat) else None
    if not ch_id:
        parts = text.split(None, 1)
        if parts and parts[0].lstrip("-").isdigit():
            ch_id, text = int(parts[0]), (parts[1] if len(parts) > 1 else "")
    matches = re.findall(r"\[([^\]]+)\]", text)
    if not ch_id or not matches:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/addchannel -100123456 [Anime] [Hindi]</code></blockquote>", reply_to=m.id)
    try:
        ch_title = (await c.get_chat(ch_id)).title or str(ch_id)
    except Exception as e:
        return await send_colored_msg(m.chat.id, f"<blockquote>❌ Channel Error: <code>{_esc(e)}</code></blockquote>", reply_to=m.id)

    db["channels"].setdefault(m.from_user.id, []).append({
        "channel_id": ch_id, "channel_title": ch_title,
        "anime": matches[0].strip(), "languages": matches[1].strip() if len(matches) > 1 else "All",
    })
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Linked <b>{_esc(matches[0])}</b> ➜ <b>{_esc(ch_title)}</b></blockquote>", reply_to=m.id)


@bot.on_message(filters.command("seechannel"))
async def cmd_seechannel(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    chs = db.get("channels", {}).get(m.from_user.id, [])
    if not chs:
        return await send_colored_msg(m.chat.id, "<blockquote>📭 No channels linked.</blockquote>", reply_to=m.id)
    lines = [f"<blockquote><b>{i}. {_esc(ch['anime'])}</b> ➜ {_esc(ch['channel_title'])} (<code>{_esc(ch['languages'])}</code>)</blockquote>" for i, ch in enumerate(chs, 1)]
    await send_colored_msg(m.chat.id, "\n".join(lines), reply_to=m.id)


@bot.on_message(filters.command("delchannel"))
async def cmd_delchannel(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    chs = db.get("channels", {}).get(m.from_user.id, [])
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/delchannel NUM</code></blockquote>", reply_to=m.id)
    idx = int(m.command[1]) - 1
    if 0 <= idx < len(chs):
        rem = chs.pop(idx)
        save_db()
        return await send_colored_msg(m.chat.id, f"<blockquote>🗑 Removed <b>{_esc(rem['anime'])}</b> channel link.</blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>❌ Invalid number.</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("thum") & filters.reply)
async def cmd_thum(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if not m.reply_to_message.photo or len(m.command) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Reply to photo: <code>/thum AnimeName</code></blockquote>", reply_to=m.id)
    name = " ".join(m.command[1:])
    db["thumbnails"].setdefault(m.from_user.id, {})[name] = m.reply_to_message.photo.file_id
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Thumbnail saved for <b>{_esc(name)}</b>!</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("seethum"))
async def cmd_seethum(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    thumbs = db.get("thumbnails", {}).get(m.from_user.id, {})
    if not thumbs:
        return await send_colored_msg(m.chat.id, "<blockquote>🖼️ No thumbnails saved.</blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>🖼️ <b>THUMBNAILS:</b>\n" + "\n".join(f"• <code>{_esc(k)}</code>" for k in thumbs) + "</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("delthum"))
async def cmd_delthum(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    name = " ".join(m.command[1:]) if len(m.command) > 1 else ""
    if name in db.get("thumbnails", {}).get(m.from_user.id, {}):
        del db["thumbnails"][m.from_user.id][name]
        save_db()
        return await send_colored_msg(m.chat.id, f"<blockquote>🗑 Deleted thumbnail: <b>{_esc(name)}</b></blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>❌ Not found.</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("setcaption"))
async def cmd_setcaption(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/setcaption &lt;b&gt;{f}&lt;/b&gt; | Ep {e} | {q}</code></blockquote>", reply_to=m.id)
    db["captions"][m.from_user.id] = parts[1]
    save_db()
    await send_colored_msg(m.chat.id, "<blockquote>✅ Custom caption saved!</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("delcaption"))
async def cmd_delcaption(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    db.get("captions", {}).pop(m.from_user.id, None)
    save_db()
    await send_colored_msg(m.chat.id, "<blockquote>♻️ Default caption restored!</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("settag"))
async def cmd_settag(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 2:
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ Usage: <code>/settag @FlyTon_Anime</code></blockquote>", reply_to=m.id)
    tag = m.text.split(None, 1)[1].strip()
    db["metadata"][m.from_user.id] = {"tag": tag}
    save_db()
    await send_colored_msg(m.chat.id, f"<blockquote>✅ Metadata tag set: <code>{_esc(tag)}</code></blockquote>", reply_to=m.id)


@bot.on_message(filters.command("cancel"))
async def cmd_cancel(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    if len(m.command) < 2:
        if not active_downloads:
            return await send_colored_msg(m.chat.id, "<blockquote>ℹ️ No active tasks.</blockquote>", reply_to=m.id)
        lines = "\n".join(f"• <b>{_esc(t.series_name)}</b> — <code>/cancel {t.cancel_id}</code>" for t in active_downloads.values())
        return await send_colored_msg(m.chat.id, f"<blockquote>📋 <b>ACTIVE TASKS</b>\n{lines}</blockquote>", reply_to=m.id)
    for t in list(active_downloads.values()):
        if t.cancel_id == m.command[1].strip():
            t.cancel()
            return await send_colored_msg(m.chat.id, f"<blockquote>✅ Cancelled <b>{_esc(t.series_name)}</b>!</blockquote>", reply_to=m.id)
    await send_colored_msg(m.chat.id, "<blockquote>❌ Task ID not found.</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("cleanupspace"))
async def cmd_cleanupspace(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)
    cnt, freed = 0, 0
    for d in [DOWNLOAD_DIR, THUMB_DIR, WORKER_DIR]:
        for root, _, files in os.walk(d):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    freed += os.path.getsize(fp)
                    os.unlink(fp)
                    cnt += 1
                except Exception:
                    pass
    await send_colored_msg(m.chat.id, f"<blockquote>🧹 Freed <code>{fmt_bytes(freed)}</code> ({cnt} files)</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("backup"))
async def cmd_backup(c, m):
    if not is_owner(m.from_user.id):
        return await send_colored_msg(m.chat.id, "<blockquote>❌ Owner only!</blockquote>", reply_to=m.id)
    save_db()
    target = BACKUP_CHANNEL or m.chat.id
    if os.path.exists(DB_FILE):
        await c.send_document(target, DB_FILE, caption=f"📦 <b>{_esc(BRAND_NAME)} DB Backup</b> — {datetime.now().strftime('%d %b %Y %H:%M')}", parse_mode=ParseMode.HTML)
        await send_colored_msg(m.chat.id, "<blockquote>✅ Backup sent! (Render रीस्टार्ट होने पर इस फाइल पर /restore रिप्लाई करके डेटा वापस ला सकते हो)</blockquote>", reply_to=m.id)


@bot.on_message(filters.command("restore") & filters.reply)
async def cmd_restore(c, m):
    if not is_owner(m.from_user.id):
        return await send_colored_msg(m.chat.id, "<blockquote>❌ Owner only!</blockquote>", reply_to=m.id)
    doc = m.reply_to_message.document
    if not doc or not (doc.file_name or "").endswith(".pkl"):
        return await send_colored_msg(m.chat.id, "<blockquote>⚠️ बैकअप वाली <code>main_db.pkl</code> फाइल पर Reply करके <code>/restore</code> भेजो।</blockquote>", reply_to=m.id)
    await c.download_media(m.reply_to_message, file_name=DB_FILE)
    load_db()
    await send_colored_msg(
        m.chat.id,
        f"<blockquote>✅ <b>DATABASE RESTORED!</b></blockquote>\n"
        f"<blockquote>🌐 Sites: <code>{len(db['websites'])}</code> | 📺 Monitored: <code>{len(db['monitored'])}</code> | ⚔️ Admins: <code>{len(db['admins'])}</code></blockquote>",
        reply_to=m.id,
    )


@bot.on_callback_query()
async def cb_router(c, q):
    uid = q.from_user.id
    if not is_authorized(uid):
        return await q.answer("🔒 Private Bot! Owner & Admin only.", show_alert=True)

    data = q.data
    back_btns = [[{"text": "🔙 Back to Main Panel", "callback_data": "ui_home", "style": "danger"}]]

    if data == "ui_home":
        txt, btns = build_home_panel(uid, q.from_user.first_name)
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, btns)
    elif data == "ui_guide_dl":
        txt = (
            "<blockquote>📺 <b>DOWNLOAD & MONITOR COMMANDS</b></blockquote>\n"
            "<blockquote>• <b>Direct URL:</b> कोई भी लिंक सीधे भेजो\n"
            "• <code>/set URL</code> — ऑटो मॉनिटर चालू करो\n"
            "• <code>/list</code> | <code>/del NUM</code>\n"
            "• <code>/batch URL 1-5</code> — बैच डाउनलोड\n"
            "• <code>/l0 URL [-e] [pass]</code> — डायरेक्ट/ZIP लीच\n"
            "• <code>/cancel [ID]</code> — टास्क कैंसिल करो</blockquote>"
        )
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, back_btns)
    elif data == "ui_sites":
        lines = [f"• <b>{_esc(v['name'])}</b> (<code>{_esc(k)}</code>): <code>{_esc(', '.join(v['patterns']))}</code>" for k, v in db.get("websites", {}).items()]
        txt = (
            "<blockquote>🌐 <b>DYNAMIC WEBSITES & DOMAINS</b></blockquote>\n"
            f"<blockquote>{chr(10).join(lines)}</blockquote>\n"
            "<blockquote>• <code>/addsite toono toono.xyz</code>\n"
            "• <code>/domain old.in new.xyz</code>\n"
            "• <code>/addcustomsite name site.com rareanimes</code></blockquote>"
        )
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, back_btns)
    elif data == "ui_guide_media":
        txt = (
            "<blockquote>📢 <b>CHANNELS, THUMBNAILS & TAGS</b></blockquote>\n"
            "<blockquote>• <code>/addchannel -100xx [Anime] [Hindi]</code>\n"
            "• <code>/seechannel</code> | <code>/delchannel NUM</code>\n"
            "• <code>/thum Name</code> (फोटो पर रिप्लाई) | <code>/seethum</code>\n"
            "• <code>/setcaption HTML</code> | <code>/settag @FlyTon_Anime</code></blockquote>"
        )
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, back_btns)
    elif data == "ui_stats":
        ram, disk, cpu = psutil.virtual_memory(), psutil.disk_usage("/"), psutil.cpu_percent(interval=0.2)
        txt = (
            "<blockquote>📊 <b>LIVE SERVER STATS</b></blockquote>\n"
            f"<blockquote>🖥 <b>Mode:</b> <code>{_esc(RUN_MODE)}</code>\n"
            f"⚡ <b>CPU:</b> <code>{cpu}%</code>\n"
            f"🧠 <b>RAM:</b> <code>{ram.used / (1024**3):.2f} / {ram.total / (1024**3):.2f} GB ({ram.percent}%)</code>\n"
            f"💾 <b>Disk:</b> <code>{disk.used / (1024**3):.2f} / {disk.total / (1024**3):.2f} GB ({disk.percent}%)</code>\n"
            f"📋 <b>Queue:</b> <code>{len(task_queue)}</code> | <b>Active:</b> <code>{len(active_downloads)}</code></blockquote>"
        )
        btns = [
            [{"text": "🔄 Refresh Stats", "callback_data": "ui_stats", "style": "success"}],
            [{"text": "🔙 Back to Main Panel", "callback_data": "ui_home", "style": "danger"}],
        ]
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, btns)
    elif data == "ui_owner":
        admins = list(db.get("admins", set()))
        adm_txt = ", ".join(f"<code>{x}</code>" for x in admins) if admins else "None"
        txt = (
            "<blockquote>👑 <b>OWNER & FRIEND ADMINS</b></blockquote>\n"
            f"<blockquote>👑 Owner: <code>{OWNER_ID}</code>\n⚔️ Admins: {adm_txt}</blockquote>\n"
            "<blockquote>• <code>/admin USER_ID</code> | <code>/radmin USER_ID</code>\n"
            "• <code>/backup</code> | <code>/restore</code> (reply to .pkl)\n"
            "• <code>/cleanupspace</code></blockquote>"
        )
        await edit_colored_msg(q.message.chat.id, q.message.id, txt, back_btns)
    await q.answer()


@bot.on_message(filters.text & filters.private & filters.regex(r"^https?://"))
async def auto_url_handler(c, m):
    if not is_authorized(m.from_user.id):
        return await deny_unauthorized(m)

    url = m.text.strip()
    site_key, site_data = detect_website(url)
    st = Status(c, m.chat.id)
    await st.create(f"<blockquote>🔍 Detected: <code>{_esc(site_data['name'] if site_data else 'Direct URL')}</code>...</blockquote>")

    title, ep_num, target_url, ep_data = "Anime Download", 1, url, None
    if site_key == "animedubhindi" and "/file/" not in url:
        title, _, ep_num, _, eps = await AnimeDubHindiFinder().get_info(url)
        ep_data = eps.get(ep_num)
    elif site_key == "rareanimes":
        title, _, ep_num, eps = await RareAnimesFinder().get_info(url)
        if eps:
            target_url = eps[-1][2]
    elif site_key == "toono" and "/series/" in url:
        title, _, ep_num, eps = await ToonoFinder().get_info(url)
        if eps:
            target_url = eps[-1][2]

    t = Task(m.from_user.id, m.chat.id, "single", target_url)
    t.series_name, t.episode, t.episode_data = title or "Anime Download", ep_num or 1, ep_data
    task_queue.append({"type": "single", "task": t, "status": st})
    await st.update(
        f"<blockquote>📥 <b>ADDED TO QUEUE (#{len(task_queue)})</b></blockquote>\n"
        f"<blockquote>🎬 <b>{_esc(t.series_name)}</b> | Ep <code>{t.episode}</code></blockquote>",
        force=True,
    )


# =============================================================================
# 11. UNIFIED STARTUP ENGINE (RENDER + VPS)
# =============================================================================
async def main():
    global download_semaphore, upload_semaphore, batch_semaphore, queue_lock, _shutdown
    if not API_ID or not API_HASH or not BOT_TOKEN or not OWNER_ID:
        print("❌ Missing API_ID, API_HASH, BOT_TOKEN, or OWNER_ID in Environment/.env!")
        return

    load_db()
    download_semaphore = asyncio.Semaphore(MAX_DOWNLOAD_WORKERS)
    upload_semaphore = asyncio.Semaphore(MAX_UPLOAD_PARALLEL)
    batch_semaphore = asyncio.Semaphore(MAX_BATCH_WORKERS)
    queue_lock = asyncio.Lock()

    web_runner = None
    if IS_RENDER or os.environ.get("PORT"):
        web_runner = await start_web_server()

    await bot.start()
    me = await bot.get_me()
    print(f"🚀 {BRAND_NAME} Bot Started as @{me.username} ({me.id}) | Mode: {RUN_MODE}")

    try:
        await bot.set_bot_commands([
            BotCommand("start", "⚡ Open Colorful Pro Control Panel"),
            BotCommand("set", "📺 Monitor Anime Series URL"),
            BotCommand("batch", "📦 Batch Download Episodes"),
            BotCommand("l0", "📥 Direct Link / ZIP Leech"),
            BotCommand("sites", "🌐 View Websites & Domains"),
            BotCommand("addsite", "➕ Add New Domain to Site"),
            BotCommand("domain", "🔄 Replace Old Domain Everywhere"),
            BotCommand("addcustomsite", "🌐 Add New Custom Website"),
            BotCommand("list", "📋 View Monitored Series"),
            BotCommand("del", "🗑 Remove Monitored Series"),
            BotCommand("addchannel", "📢 Link Channel with Audio Filter"),
            BotCommand("seechannel", "📋 View Linked Channels"),
            BotCommand("thum", "🖼️ Set Custom Thumbnail"),
            BotCommand("setcaption", "📝 Set Custom HTML Caption"),
            BotCommand("settag", "🏷️ Set Metadata Tag"),
            BotCommand("admin", "👑 Add Friend as Admin"),
            BotCommand("radmin", "🗑 Remove Admin Friend"),
            BotCommand("backup", "📦 Export Database Backup"),
            BotCommand("restore", "♻️ Restore Database (.pkl)"),
            BotCommand("cancel", "❌ Cancel Active Download"),
            BotCommand("cleanupspace", "🧹 Free Temp Disk Space"),
        ])
    except Exception as e:
        print(f"[Menu Sync Info] {e}")

    bg_tasks = [asyncio.create_task(download_worker(i)) for i in range(1, MAX_DOWNLOAD_WORKERS + 1)]
    bg_tasks.append(asyncio.create_task(monitor_loop()))

    await idle()

    _shutdown = True
    for task in bg_tasks:
        task.cancel()
    await bot.stop()
    if web_runner:
        await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
