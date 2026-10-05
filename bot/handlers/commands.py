import time
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from bot.config import is_user_authorized, MOVIES_DIR, MUSIC_DIR
from bot.utils.sys_stats import get_system_stats

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        await update.message.reply_text("⛔ <b>Access Denied:</b> Unauthorized User.", parse_mode=ParseMode.HTML)
        return

    text = (
        f"👋 <b>Welcome, {user.first_name}!</b>\n\n"
        f"🤖 I am your <b>Media Downloader & Jellyfin Ingestion Bot</b>.\n\n"
        f"<b>Features:</b>\n"
        f"• <b>Smart URL Detection:</b> Auto-detects direct streams vs YouTube.\n"
        f"• <b>Local Bot API:</b> High-speed Telegram file uploads up to 2GB.\n"
        f"• <b>MLTB Progress UI:</b> Live percentage, speed, ETA, and cancellation.\n"
        f"• <b>Direct Jellyfin Ingestion:</b> Automatically moves media to <code>/movies</code> or <code>/music</code>.\n\n"
        f"<b>Commands:</b>\n"
        f"• /stats or /server — View Dell server hardware & network stats\n"
        f"• /ping — Check bot latency\n"
        f"• /help — Show help guide"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    text = (
        f"📖 <b>How to use this bot:</b>\n\n"
        f"1. <b>Send Any URL:</b>\n"
        f"   • <i>YouTube/Social Video:</i> Select desired quality (1080p, 720p, 480p, MP3).\n"
        f"   • <i>Direct Stream/Cloudflare link:</i> Click <b>📥 Download to Server</b>.\n\n"
        f"2. <b>Send Any Media File:</b>\n"
        f"   • Documents & Videos are saved to <code>{MOVIES_DIR}</code>\n"
        f"   • Audio files are saved to <code>{MUSIC_DIR}</code>\n\n"
        f"3. <b>Monitor Progress:</b>\n"
        f"   • Progress bars update live with speed, ETA, and cancel support."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    stats_msg = get_system_stats(movies_dir=MOVIES_DIR, music_dir=MUSIC_DIR)
    await update.message.reply_text(stats_msg, parse_mode=ParseMode.HTML)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    msg = await update.message.reply_text("🏓 <i>Pinging...</i>", parse_mode=ParseMode.HTML)
    latency = int((time.time() - start) * 1000)
    await msg.edit_text(f"🏓 <b>Pong!</b> <code>{latency}ms</code>", parse_mode=ParseMode.HTML)
