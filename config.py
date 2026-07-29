import os

# --- Bot tokens (create two bots with @BotFather) ---
DOWNLOAD_BOT_TOKEN = os.environ.get("DOWNLOAD_BOT_TOKEN", "8798971648:AAFaPeliozXliAo3FvLhtZ3sxdRn1eLeRpw")
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN", "8647632292:AAF7lPz9nQsqaPadb1b1cLCi94mlsYQHkOI")

# Your personal Telegram numeric ID(s) - the only people allowed to use the admin bot.
# Get your ID by messaging @userinfobot on Telegram.
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "6594079594").split(",") if x.strip()]

# On Railway, set DB_PATH and QR_DIR to paths inside your mounted Volume
# (e.g. /data/bot.db and /data/qr_codes) so they survive redeploys.
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "bot.db"))
QR_DIR = os.environ.get("QR_DIR", os.path.join(os.path.dirname(__file__), "qr_codes"))
os.makedirs(QR_DIR, exist_ok=True)

# Path to a Netscape-format cookies.txt file, used so yt-dlp can pass YouTube's
# bot-check on server IPs. Set via the admin bot's /setcookies command, or
# point this at a path inside your Railway volume (e.g. /data/cookies.txt).
COOKIES_PATH = os.environ.get(
    "COOKIES_PATH", os.path.join(os.path.dirname(__file__), "cookies.txt")
)

MAX_FILE_MB = 49  # Telegram bot upload limit

# --- Subscription tiers ---
# max_height controls which video qualities a tier is allowed to pick.
# price is in USD/month, shown to the user during /upgrade.
TIERS = {
    "free": {
        "label": "Free",
        "daily_limit": 5,
        "max_height": 720,
        "price": 0,
    },
    "premium2": {
        "label": "Premium ($2/mo)",
        "daily_limit": 10,
        "max_height": 1080,
        "price": 2,
    },
    "premium5": {
        "label": "Premium+ ($5/mo, 4K)",
        "daily_limit": 30,
        "max_height": 2160,
        "price": 5,
    },
}

SUBSCRIPTION_DAYS = 30  # length of one paid period

# Quality buttons shown to users, ordered high -> low.
# (internal_key, height, display_label)
QUALITY_OPTIONS = [
    ("4k", 2160, "🎬 4K (2160p)"),
    ("1080", 1080, "🎬 1080p"),
    ("720", 720, "🎬 720p"),
    ("480", 480, "🎬 480p"),
]
