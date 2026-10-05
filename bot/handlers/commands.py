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
        f"📖 <b>How to use this bot (MLTB Style):</b>\n\n"
        f"1. <b>Send Any URL:</b>\n"
        f"   • <i>YouTube/Media:</i> Auto-detects real title, offers full quality grid.\n"
        f"   • <i>Direct Stream:</i> Click <b>📥 Download to Server</b>.\n"
        f"   • <i>Rename:</i> Send <code>link | new_name.mkv</code> or click <b>✏️ Rename</b>.\n\n"
        f"2. <b>Send Any Media File:</b>\n"
        f"   • Documents & Videos ➔ <code>{MOVIES_DIR}</code>\n"
        f"   • Audio files ➔ <code>{MUSIC_DIR}</code>\n"
        f"   • Add a message caption to rename the file!\n\n"
        f"3. <b>Cancellation:</b>\n"
        f"   • Reply to any progress bar with <code>/cancel</code>\n"
        f"   • Use <code>/cancel &lt;task_id&gt;</code>\n"
        f"   • Use <code>/cancel all</code> to stop all downloads.\n\n"
        f"4. <b>Server Stats:</b>\n"
        f"   • Use <code>/stats</code> or <code>/server</code>"
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

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    from bot.core.task_manager import task_manager

    # 1. Check if user replied to a progress message with /cancel
    if update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        task_id = await task_manager.cancel_by_message(update.effective_chat.id, replied_msg_id)
        if task_id:
            await update.message.reply_text(f"🛑 <b>Cancelled task:</b> <code>{task_id}</code>", parse_mode=ParseMode.HTML)
            return
        else:
            await update.message.reply_text("⚠️ <i>No active download task found for that message.</i>", parse_mode=ParseMode.HTML)
            return

    # 2. Check if argument provided (/cancel <task_id> or /cancel all)
    args = context.args
    if args:
        target = args[0].strip().lower()
        if target == "all":
            count = await task_manager.cancel_all()
            await update.message.reply_text(f"🛑 <b>Cancelled {count} active download task(s).</b>", parse_mode=ParseMode.HTML)
            return
        else:
            cancelled = await task_manager.cancel_task(target)
            if cancelled:
                await update.message.reply_text(f"🛑 <b>Cancelled task:</b> <code>{target}</code>", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"⚠️ <i>Task <code>{target}</code> not found or already completed.</i>", parse_mode=ParseMode.HTML)
            return

    # 3. If no argument and not replying: check active tasks
    tasks = await task_manager.get_all_tasks()
    active = [t for t in tasks.values() if not t.is_cancelled]

    if not active:
        await update.message.reply_text("ℹ️ <i>No active download tasks currently running.</i>", parse_mode=ParseMode.HTML)
        return

    if len(active) == 1:
        single_task = active[0]
        await task_manager.cancel_task(single_task.task_id)
        await update.message.reply_text(
            f"🛑 <b>Cancelled task:</b> <code>{single_task.task_id}</code> (<code>{single_task.name}</code>)",
            parse_mode=ParseMode.HTML
        )
        return

    # Multiple tasks active: list them
    lines = ["<b>Active Tasks:</b>"]
    for t in active:
        lines.append(f"• <code>{t.task_id}</code> — <b>{t.name}</b> (<code>/cancel {t.task_id}</code>)")
    lines.append("\n<i>To cancel, reply /cancel to a progress message or use <code>/cancel &lt;task_id&gt;</code>, or <code>/cancel all</code>.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
