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

    # 3. Rename requested
    if data.startswith("rename:"):
        token = data.split(":", 1)[1]
        if token in pending_links:
            context.user_data["waiting_rename_token"] = token
            await query.message.reply_text(
                "✏️ <b>Send the new filename for this download:</b>",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.answer("Link session expired. Please resend the URL.", show_alert=True)
        return

    # 4. Start Direct Download
    if data.startswith("start_direct:"):
        token = data.split(":", 1)[1]
        link_info = pending_links.pop(token, None)
        if not link_info:
            await query.message.edit_text("⚠️ <i>Link session expired. Please resend the URL.</i>", parse_mode=ParseMode.HTML)
            return

        filename = link_info.get("custom_name") or link_info.get("filename") or "downloaded_stream"
        url = link_info["url"]

        task = await task_manager.register_task(
            name=filename,
            user_id=user.id,
            user_name=user.first_name,
            engine="Direct-Stream",
            message=query.message
        )

        # Immediately clear quality/download buttons and show initialization state with Cancel command instruction
        await query.message.edit_text(
            f"⏳ <b>Initializing direct stream...</b>\n"
            f"<b>File:</b> <code>{filename}</code>\n"
            f"<b>Task ID:</b> <code>{task.task_id}</code>\n"
            f"<i>Connecting to remote host...</i>",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )

        # Launch async task in background
        asyncio.create_task(run_direct_download(url=url, filename=filename, task=task))
        return

    # 5. Start yt-dlp Media Download
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
        custom_name = link_info.get("custom_name")
        task_name = custom_name or link_info.get("filename") or f"Media [{quality.upper()}]"

        task = await task_manager.register_task(
            name=task_name,
            user_id=user.id,
            user_name=user.first_name,
            engine="yt-dlp",
            message=query.message
        )

        # Immediately clear quality selection buttons and show extraction state with Cancel command instruction
        await query.message.edit_text(
            f"⏳ <b>Initializing {quality.upper()} download...</b>\n"
            f"<b>Title:</b> <code>{task_name}</code>\n"
            f"<b>Task ID:</b> <code>{task.task_id}</code>\n"
            f"<i>Extracting YouTube stream & formats...</i>",
            reply_markup=None,
            parse_mode=ParseMode.HTML
        )

        # Launch async task in background
        asyncio.create_task(run_ytdl_download(url=url, quality_key=quality, task=task, custom_name=custom_name))
        return
