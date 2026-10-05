import asyncio
import os
import uuid
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from bot.config import is_user_authorized
from bot.utils.url_detector import is_url, detect_url_type
from bot.utils.formatters import get_readable_file_size, sanitize_filename
from bot.logger import logger

# In-memory store for pending user URL choices
pending_links = {}

def fetch_media_title(target_url: str) -> str:
    """Extracts media title from YouTube/social platforms using yt-dlp metadata."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            return info.get('title') or "Video Stream"
    except Exception as e:
        logger.debug(f"Title extraction failed: {e}")
        return "Video Stream"

async def link_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    raw_text = update.message.text.strip()

    # 1. Check if user is currently answering a Rename prompt
    rename_token = context.user_data.pop("waiting_rename_token", None)
    if rename_token and rename_token in pending_links:
        new_name = sanitize_filename(raw_text)
        pending_links[rename_token]["filename"] = new_name
        pending_links[rename_token]["custom_name"] = new_name
        await update.message.reply_text(
            f"✏️ <b>Filename updated to:</b> <code>{new_name}</code>\n"
            f"Please proceed with the download selection above.",
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Check for inline custom name: "url | custom_name" or "url -n custom_name"
    custom_name = None
    if " | " in raw_text:
        parts = raw_text.split(" | ", 1)
        url_text = parts[0].strip()
        custom_name = sanitize_filename(parts[1].strip())
    elif " -n " in raw_text:
        parts = raw_text.split(" -n ", 1)
        url_text = parts[0].strip()
        custom_name = sanitize_filename(parts[1].strip())
    else:
        url_text = raw_text

    if not is_url(url_text):
        return

    status_wait = await update.message.reply_text("🔍 <i>Inspecting URL...</i>", parse_mode=ParseMode.HTML)
    info = await detect_url_type(url_text)
    await status_wait.delete()

    link_token = str(uuid.uuid4())[:8]

    if info["type"] == "direct":
        size_str = get_readable_file_size(info.get("size"))
        filename = custom_name or info.get("filename") or "downloaded_stream"

        pending_links[link_token] = {
            "type": "direct",
            "url": info["url"],
            "filename": filename,
            "custom_name": custom_name,
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
            [
                InlineKeyboardButton("✏️ Rename", callback_data=f"rename:{link_token}"),
                InlineKeyboardButton("❌ Dismiss", callback_data=f"dismiss:{link_token}")
            ]
        ]
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    else:
        # YouTube or general media extractor URL
        media_title = custom_name
        if not media_title:
            status_title = await update.message.reply_text("🎬 <i>Extracting video title...</i>", parse_mode=ParseMode.HTML)
            media_title = await asyncio.to_thread(fetch_media_title, url_text)
            await status_title.delete()

        clean_title = sanitize_filename(media_title)

        pending_links[link_token] = {
            "type": "media",
            "url": url_text,
            "filename": clean_title,
            "custom_name": clean_title,
            "user_id": user.id,
            "user_name": user.first_name
        }

        caption = (
            f"🎬 <b>Media Stream Detected</b>\n\n"
            f"<b>Title:</b> <code>{clean_title}</code>\n\n"
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
            [
                InlineKeyboardButton("✏️ Rename", callback_data=f"rename:{link_token}"),
                InlineKeyboardButton("❌ Dismiss", callback_data=f"dismiss:{link_token}")
            ]
        ]
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
