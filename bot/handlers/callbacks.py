import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from bot.config import is_user_authorized
from bot.core.task_manager import task_manager
from bot.handlers.links import pending_links
from bot.downloaders.direct import run_direct_download
from bot.downloaders.ytdl import run_ytdl_download
from bot.logger import logger

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not is_user_authorized(user.id):
        return

    data = query.data or ""

    # 1. Dismiss / Cancel prompt
    if data.startswith("dismiss:"):
        token = data.split(":", 1)[1]
        pending_links.pop(token, None)
        await query.message.delete()
        return

    # 2. Cancel active download task
    if data.startswith("cancel_task:"):
        task_id = data.split(":", 1)[1]
        cancelled = await task_manager.cancel_task(task_id)
        if cancelled:
            await query.message.edit_text("⏳ <i>Cancelling download task...</i>", parse_mode=ParseMode.HTML)
        else:
            await query.answer("Task not found or already completed.", show_alert=True)
        return

    # 3. Start Direct Download
    if data.startswith("start_direct:"):
        token = data.split(":", 1)[1]
        link_info = pending_links.pop(token, None)
        if not link_info:
            await query.message.edit_text("⚠️ <i>Link session expired. Please resend the URL.</i>", parse_mode=ParseMode.HTML)
            return

        filename = link_info.get("filename") or "downloaded_stream"
        url = link_info["url"]

        task = await task_manager.register_task(
            name=filename,
            user_id=user.id,
            user_name=user.first_name,
            engine="Direct-Stream",
            message=query.message
        )

        # Immediately clear quality/download buttons and show initialization state with Cancel button
        cancel_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_task:{task.task_id}")
        ]])
        await query.message.edit_text(
            f"⏳ <b>Initializing direct stream...</b>\n"
            f"<b>File:</b> <code>{filename}</code>\n"
            f"<i>Connecting to remote host...</i>",
            reply_markup=cancel_markup,
            parse_mode=ParseMode.HTML
        )

        # Launch async task in background
        asyncio.create_task(run_direct_download(url=url, filename=filename, task=task))
        return

    # 4. Start yt-dlp Media Download
    if data.startswith("start_ytdl:"):
        parts = data.split(":")
        if len(parts) < 3:
            return
        quality = parts[1]
        token = parts[2]

        link_info = pending_links.pop(token, None)
        if not link_info:
            await query.message.edit_text("⚠️ <i>Link session expired. Please resend the URL.</i>", parse_mode=ParseMode.HTML)
            return

        url = link_info["url"]
        task_name = f"Media [{quality.upper()}]"

        task = await task_manager.register_task(
            name=task_name,
            user_id=user.id,
            user_name=user.first_name,
            engine="yt-dlp",
            message=query.message
        )

        # Immediately clear quality selection buttons and show extraction state with Cancel button
        cancel_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_task:{task.task_id}")
        ]])
        await query.message.edit_text(
            f"⏳ <b>Initializing {quality.upper()} download...</b>\n"
            f"<i>Extracting YouTube stream & formats...</i>",
            reply_markup=cancel_markup,
            parse_mode=ParseMode.HTML
        )

        # Launch async task in background
        asyncio.create_task(run_ytdl_download(url=url, quality_key=quality, task=task))
        return
