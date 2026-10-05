import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from bot.config import is_user_authorized
from bot.utils.url_detector import is_url, detect_url_type
from bot.utils.formatters import get_readable_file_size

# In-memory store for pending user URL choices
pending_links = {}

async def link_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    text = update.message.text.strip()
    if not is_url(text):
        return

    status_wait = await update.message.reply_text("🔍 <i>Inspecting URL...</i>", parse_mode=ParseMode.HTML)
    info = await detect_url_type(text)
    await status_wait.delete()

    link_token = str(uuid.uuid4())[:8]

    if info["type"] == "direct":
        size_str = get_readable_file_size(info.get("size"))
        filename = info.get("filename") or "downloaded_file"

        pending_links[link_token] = {
            "type": "direct",
            "url": info["url"],
            "filename": filename,
            "user_id": user.id,
            "user_name": user.first_name
        }

        caption = (
            f"🔗 <b>Direct File Detected</b>\n\n"
            f"<b>┌ Name:</b> <code>{filename}</code>\n"
            f"<b>├ Size:</b> {size_str}\n"
            f"<b>└ Engine:</b> Direct-Stream"
        )
        keyboard = [
            [InlineKeyboardButton("📥 Download to Server", callback_data=f"start_direct:{link_token}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"dismiss:{link_token}")]
        ]
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    else:
        # YouTube or general media extractor URL
        pending_links[link_token] = {
            "type": "media",
            "url": text,
            "user_id": user.id,
            "user_name": user.first_name
        }

        caption = (
            f"🎬 <b>Media Stream Detected</b>\n\n"
            f"Select desired download quality:"
        )
        keyboard = [
            [
                InlineKeyboardButton("🌟 Best Video", callback_data=f"start_ytdl:best:{link_token}"),
                InlineKeyboardButton("🎵 Best MP3", callback_data=f"start_ytdl:mp3:{link_token}")
            ],
            [
                InlineKeyboardButton("🎬 4K (2160p)", callback_data=f"start_ytdl:2160:{link_token}"),
                InlineKeyboardButton("🎬 2K (1440p)", callback_data=f"start_ytdl:1440:{link_token}")
            ],
            [
                InlineKeyboardButton("🎬 1080p (FHD)", callback_data=f"start_ytdl:1080:{link_token}"),
                InlineKeyboardButton("🎬 720p (HD)", callback_data=f"start_ytdl:720:{link_token}")
            ],
            [
                InlineKeyboardButton("🎬 480p (SD)", callback_data=f"start_ytdl:480:{link_token}"),
                InlineKeyboardButton("🎬 360p", callback_data=f"start_ytdl:360:{link_token}")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"dismiss:{link_token}")]
        ]
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
