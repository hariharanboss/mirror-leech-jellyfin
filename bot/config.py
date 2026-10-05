import os
import sys
from dotenv import load_dotenv

# Load .env file if available
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("CRITICAL: BOT_TOKEN is missing! Set it in your .env file.", file=sys.stderr)

# Local Telegram Bot API endpoint (e.g. http://telegram-bot-api:8081)
BOT_API_URL = os.getenv("BOT_API_URL", "http://telegram-bot-api:8081").strip().rstrip("/")

# Target directories for Jellyfin
MOVIES_DIR = os.getenv("MOVIES_DIR", "/movies").strip()
MUSIC_DIR = os.getenv("MUSIC_DIR", "/music").strip()

# Create directories if they do not exist
os.makedirs(MOVIES_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)

# Authorized users (empty list means all users are permitted)
ALLOWED_USERS_RAW = os.getenv("ALLOWED_USERS", "").strip()
ALLOWED_USERS = set(
    int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()
)

def is_user_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS
