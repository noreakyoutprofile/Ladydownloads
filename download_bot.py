import os
import re
import logging
import asyncio
from tempfile import TemporaryDirectory

import yt_dlp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Bot,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
import db
from strings import t

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://\S+")

# in-memory session state per chat
pending_urls = {}       # chat_id -> url waiting for a quality choice
awaiting_proof = {}      # chat_id -> tier_requested (waiting for a payment screenshot)


def user_display_name(update: Update) -> str:
    u = update.effective_user
    return u.username or (u.first_name or "")


def user_lang(user_id: int) -> str:
    s = db.get_user_status(user_id)
    return s["language"] if s else "en"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.get_or_create_user(update.effective_user.id, user_display_name(update))
    lang = user_lang(update.effective_user.id)
    await update.message.reply_text(t(lang, "welcome"))


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.get_or_create_user(update.effective_user.id, user_display_name(update))
    lang = user_lang(update.effective_user.id)
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="lang_en"),
            InlineKeyboardButton("ខ្មែរ", callback_data="lang_km"),
        ]
    ]
    await update.message.reply_text(t(lang, "choose_language"), reply_markup=InlineKeyboardMarkup(keyboard))


async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    new_lang = query.data.replace("lang_", "")
    db.set_language(update.effective_user.id, new_lang)
    await query.edit_message_text(t(new_lang, "language_set"))


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.get_or_create_user(update.effective_user.id, user_display_name(update))
    s = db.get_user_status(update.effective_user.id)
    lang = s["language"]
    text = t(
        lang,
        "status_lines",
        tier_label=s["tier_label"],
        daily_count=s["daily_count"],
        daily_limit=s["daily_limit"],
        remaining=s["remaining"],
        max_height=s["max_height"],
    )
    if s["expiry_date"]:
        text += "\n" + t(lang, "status_expiry", expiry_date=s["expiry_date"])
    await update.message.reply_text(text)


async def upgrade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.get_or_create_user(update.effective_user.id, user_display_name(update))
    lang = user_lang(update.effective_user.id)
    keyboard = []
    for key, info in config.TIERS.items():
        if key == "free":
            continue
        keyboard.append(
            [InlineKeyboardButton(
                t(lang, "plan_button", label=info["label"], daily_limit=info["daily_limit"]),
                callback_data=f"plan_{key}",
            )]
        )
    await update.message.reply_text(
        t(lang, "upgrade_choose_plan"), reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def plan_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tier_key = query.data.replace("plan_", "")
    info = config.TIERS[tier_key]
    chat_id = update.effective_chat.id
    lang = user_lang(update.effective_user.id)

    qr_path = os.path.join(config.QR_DIR, "qr.jpg")
    caption = t(lang, "payment_caption", label=info["label"], price=info["price"])
    if os.path.exists(qr_path):
        with open(qr_path, "rb") as f:
            await query.message.reply_photo(photo=f, caption=caption)
    else:
        await query.message.reply_text(caption + t(lang, "payment_no_qr"))

    awaiting_proof[chat_id] = tier_key


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tier_requested = awaiting_proof.get(chat_id)
    if not tier_requested:
        return  # not expecting a payment proof from this user right now

    user = update.effective_user
    lang = user_lang(user.id)
    request_id = db.create_payment_request(user.id, user_display_name(update), tier_requested)
    awaiting_proof.pop(chat_id, None)

    await update.message.reply_text(t(lang, "proof_received"))

    # Forward the proof + an approve/reject prompt to the admin, via the admin bot
    info = config.TIERS[tier_requested]
    caption = (
        f"🆕 Payment request #{request_id}\n"
        f"User: @{user.username or user.id} (id: {user.id})\n"
        f"Plan: {info['label']} (${info['price']})\n\n"
        f"Approve or reject in the admin bot."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{request_id}"),
            ]
        ]
    )
    admin_bot = Bot(token=config.ADMIN_BOT_TOKEN)
    photo_file_id = update.message.photo[-1].file_id
    photo_file = await context.bot.get_file(photo_file_id)

    with TemporaryDirectory() as tmp:
        local_path = os.path.join(tmp, "proof.jpg")
        await photo_file.download_to_drive(local_path)
        for admin_id in config.ADMIN_IDS:
            try:
                with open(local_path, "rb") as f:
                    await admin_bot.send_photo(
                        chat_id=admin_id, photo=f, caption=caption, reply_markup=keyboard
                    )
            except Exception:
                logger.exception("Failed to notify admin %s", admin_id)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = URL_REGEX.search(text)
    user_id = update.effective_user.id
    db.get_or_create_user(user_id, user_display_name(update))
    lang = user_lang(user_id)

    if not match:
        await update.message.reply_text(t(lang, "invalid_link"))
        return

    s = db.get_user_status(user_id)

    if s["banned"]:
        await update.message.reply_text(t(lang, "banned"))
        return

    if s["remaining"] <= 0:
        await update.message.reply_text(
            t(lang, "quota_exceeded", daily_limit=s["daily_limit"], tier_label=s["tier_label"])
        )
        return

    url = match.group(0)
    chat_id = update.effective_chat.id
    pending_urls[chat_id] = url

    max_h = s["max_height"]
    keyboard_rows = []
    row = []
    for key, height, label in config.QUALITY_OPTIONS:
        if height <= max_h:
            row.append(InlineKeyboardButton(label, callback_data=f"video_{key}"))
        else:
            row.append(InlineKeyboardButton(f"🔒 {label}", callback_data=f"locked_{key}"))
        if len(row) == 2:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)
    keyboard_rows.append([InlineKeyboardButton(t(lang, "audio_label"), callback_data="audio_mp3")])

    await update.message.reply_text(
        t(lang, "choose_quality", remaining=s["remaining"], daily_limit=s["daily_limit"]),
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


def build_ydl_opts(choice_key: str, height: int, out_dir: str) -> dict:
    opts = {
        "outtmpl": os.path.join(out_dir, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"tiktok": {"webpage_download": ["true"]}},
    }
    if os.path.exists(config.COOKIES_PATH):
        opts["cookiefile"] = config.COOKIES_PATH
    if choice_key == "audio_mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    else:
        opts["format"] = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        opts["merge_output_format"] = "mp4"
    return opts


def _download(url: str, opts: dict) -> str:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


async def handle_quality_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    lang = user_lang(user_id)

    if data.startswith("locked_"):
        await query.answer(t(lang, "locked_alert"), show_alert=True)
        return

    await query.answer()
    chat_id = update.effective_chat.id
    url = pending_urls.get(chat_id)
    if not url:
        await query.edit_message_text(t(lang, "link_expired"))
        return

    s = db.get_user_status(user_id)
    if s["remaining"] <= 0:
        await query.edit_message_text(t(lang, "out_of_downloads"))
        return

    height = 0
    if data.startswith("video_"):
        key = data.replace("video_", "")
        height = dict((k, h) for k, h, _ in config.QUALITY_OPTIONS)[key]
        height = min(height, s["max_height"])

    await query.edit_message_text(t(lang, "downloading"))

    with TemporaryDirectory() as tmp_dir:
        opts = build_ydl_opts(data, height, tmp_dir)
        try:
            loop = asyncio.get_event_loop()
            filename = await loop.run_in_executor(None, _download, url, opts)

            if data == "audio_mp3":
                base, _ = os.path.splitext(filename)
                mp3_path = base + ".mp3"
                if os.path.exists(mp3_path):
                    filename = mp3_path

            if not os.path.exists(filename):
                files = os.listdir(tmp_dir)
                if not files:
                    raise FileNotFoundError("No output file was produced.")
                filename = os.path.join(tmp_dir, files[0])

            size_mb = os.path.getsize(filename) / (1024 * 1024)
            if size_mb > config.MAX_FILE_MB:
                await query.message.reply_text(
                    t(lang, "file_too_large", size_mb=size_mb, max_mb=config.MAX_FILE_MB)
                )
                return

            with open(filename, "rb") as f:
                if data == "audio_mp3":
                    await query.message.reply_audio(audio=f)
                else:
                    await query.message.reply_video(video=f, supports_streaming=True)

            db.increment_download_count(user_id)
            new_status = db.get_user_status(user_id)
            await query.edit_message_text(
                t(lang, "done", remaining=new_status["remaining"], daily_limit=new_status["daily_limit"])
            )
        except Exception as e:
            logger.exception("Download failed")
            await query.edit_message_text(t(lang, "failed", error=str(e)))
        finally:
            pending_urls.pop(chat_id, None)


def main():
    db.init_db()
    if config.DOWNLOAD_BOT_TOKEN == "PUT_DOWNLOAD_BOT_TOKEN_HERE":
        raise SystemExit("Set DOWNLOAD_BOT_TOKEN env var first.")

    app = ApplicationBuilder().token(config.DOWNLOAD_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("upgrade", upgrade_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CallbackQueryHandler(language_choice, pattern=r"^lang_"))
    app.add_handler(CallbackQueryHandler(plan_choice, pattern=r"^plan_"))
    app.add_handler(
        CallbackQueryHandler(handle_quality_choice, pattern=r"^(video_|audio_mp3|locked_)")
    )
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info("Download bot starting...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
