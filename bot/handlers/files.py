import asyncio
import os
import shutil
import time
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from bot.config import is_user_authorized, MOVIES_DIR, MUSIC_DIR
from bot.core.task_manager import task_manager
from bot.utils.formatters import (
    get_readable_file_size,
    get_readable_time,
    sanitize_filename,
    build_status_message
)
from bot.logger import logger

AUDIO_MIME_TYPES = ("audio/", "voice/")

async def file_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_authorized(user.id):
        return

    message = update.message
    # Determine which file type was uploaded
    media_obj = message.document or message.video or message.audio or message.voice
    if not media_obj:
        return

    # Extract or infer filename
    raw_name = getattr(media_obj, "file_name", None)
    if not raw_name:
        mime = getattr(media_obj, "mime_type", "")
        if "audio" in mime or message.voice:
            raw_name = f"audio_{int(time.time())}.mp3"
        elif "video" in mime or message.video:
            raw_name = f"video_{int(time.time())}.mp4"
        else:
            raw_name = f"file_{int(time.time())}.bin"

    # Support custom filename via Telegram message caption
    if message.caption and message.caption.strip():
        caption_clean = sanitize_filename(message.caption.strip())
        orig_base, orig_ext = os.path.splitext(raw_name)
        cap_base, cap_ext = os.path.splitext(caption_clean)
        if not cap_ext and orig_ext:
            caption_clean = f"{caption_clean}{orig_ext}"
        filename = caption_clean
    else:
        filename = sanitize_filename(raw_name)

    mime_type = getattr(media_obj, "mime_type", "") or ""

    # Choose destination based on type
    is_audio = message.audio or message.voice or any(mime_type.startswith(p) for p in AUDIO_MIME_TYPES)
    dest_dir = MUSIC_DIR if is_audio else MOVIES_DIR
    os.makedirs(dest_dir, exist_ok=True)
    target_filepath = os.path.join(dest_dir, filename)

    status_msg = await message.reply_text(
        f"📥 <i>Initiating transfer for {filename} ({get_readable_file_size(media_obj.file_size)})...</i>",
        parse_mode=ParseMode.HTML
    )
    start_time = time.time()

    task = await task_manager.register_task(
        name=filename,
        user_id=user.id,
        user_name=user.first_name,
        engine="Local-Bot-API",
        message=status_msg
    )

    total_size = media_obj.file_size
    done_event = asyncio.Event()

    async def poll_local_api_progress():
        while not done_event.is_set():
            await asyncio.sleep(2.0)
            if done_event.is_set() or task.is_cancelled:
                break

            current_size = 0
            api_dir = "/var/lib/telegram-bot-api"
            if os.path.exists(api_dir):
                try:
                    latest_mtime = 0
                    latest_file = None
                    for root, _, files in os.walk(api_dir):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                m = os.path.getmtime(fp)
                                if m > latest_mtime and m >= start_time - 10:
                                    latest_mtime = m
                                    latest_file = fp
                            except Exception:
                                pass
                    if latest_file and os.path.exists(latest_file):
                        current_size = os.path.getsize(latest_file)
                except Exception:
                    pass

            now = time.time()
            speed = current_size / (now - start_time) if (now - start_time) > 0 else 0
            status_text = build_status_message(
                name=filename,
                status="Receiving",
                downloaded_bytes=current_size,
                total_bytes=total_size,
                speed=speed,
                start_time=start_time,
                engine="Local-Bot-API",
                task_id=task.task_id,
                user_name=user.first_name,
                user_id=user.id
            )
            await task_manager.safe_edit_status(task, status_text)

    monitor_task = asyncio.create_task(poll_local_api_progress())

    try:
        # 30-minute timeout for large files over local API
        tg_file = await media_obj.get_file(read_timeout=1800, write_timeout=1800)
        done_event.set()
        monitor_task.cancel()
        file_path = tg_file.file_path

        if task.is_cancelled:
            await status_msg.edit_text("❌ <b>Transfer Cancelled by User.</b>", parse_mode=ParseMode.HTML)
            return

        # Case 1: Local Telegram Bot API returned a local disk path
        if file_path and os.path.exists(file_path):
            logger.info(f"Local Telegram Bot API direct path detected: {file_path}")

            # Show moving state
            moving_text = build_status_message(
                name=filename,
                status="Moving to Jellyfin",
                downloaded_bytes=total_size or os.path.getsize(file_path),
                total_bytes=total_size or os.path.getsize(file_path),
                speed=0,
                start_time=start_time,
                engine="Local-Bot-API",
                task_id=task.task_id,
                user_name=user.first_name,
                user_id=user.id
            )
            await task_manager.safe_edit_status(task, moving_text, force=True)

            # Avoid file overwrites
            if os.path.exists(target_filepath):
                base, ext = os.path.splitext(filename)
                target_filepath = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext}")

            # Instant move on the same filesystem
            shutil.move(file_path, target_filepath)

            file_size = os.path.getsize(target_filepath)
            elapsed_str = get_readable_time(int(time.time() - start_time))

            await status_msg.edit_text(
                f"✅ <b>File Ingested into Jellyfin!</b>\n\n"
                f"<b>┌ Name:</b> <code>{os.path.basename(target_filepath)}</code>\n"
                f"<b>├ Size:</b> {get_readable_file_size(file_size)}\n"
                f"<b>├ Time:</b> {elapsed_str}\n"
                f"<b>├ Engine:</b> <code>Zero-Copy Local API</code>\n"
                f"<b>└ Saved to:</b> <code>{target_filepath}</code>",
                parse_mode=ParseMode.HTML
            )
            return

        # Case 2: Fallback streaming download with progress bar
        temp_dest = os.path.join(dest_dir, f".tmp_{task.task_id}_{filename}")
        task.temp_filepath = temp_dest

        async def progress_hook(current, total):
            if task.is_cancelled:
                return
            now = time.time()
            speed = current / (now - start_time) if (now - start_time) > 0 else 0
            text = build_status_message(
                name=filename,
                status="Receiving",
                downloaded_bytes=current,
                total_bytes=total or total_size,
                speed=speed,
                start_time=start_time,
                engine="Local-API-Stream",
                task_id=task.task_id,
                user_name=user.first_name,
                user_id=user.id
            )
            await task_manager.safe_edit_status(task, text)

        await tg_file.download_to_drive(
            custom_path=temp_dest,
            read_timeout=1800,
            write_timeout=1800
        )

        if task.is_cancelled:
            task.cancel()
            await status_msg.edit_text("❌ <b>Transfer Cancelled.</b>", parse_mode=ParseMode.HTML)
            return

        if os.path.exists(target_filepath):
            base, ext = os.path.splitext(filename)
            target_filepath = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext}")

        shutil.move(temp_dest, target_filepath)
        task.temp_filepath = None

        elapsed_str = get_readable_time(int(time.time() - start_time))
        final_size = os.path.getsize(target_filepath)

        await status_msg.edit_text(
            f"✅ <b>Saved to Server!</b>\n\n"
            f"<b>┌ Name:</b> <code>{os.path.basename(target_filepath)}</code>\n"
            f"<b>├ Size:</b> {get_readable_file_size(final_size)}\n"
            f"<b>├ Time:</b> {elapsed_str}\n"
            f"<b>└ Saved to:</b> <code>{target_filepath}</code>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error handling Telegram file: {e}", exc_info=True)
        if not task.is_cancelled:
            err_str = str(e)
            if "File is too big" in err_str:
                msg = (
                    "❌ <b>File is too big for Cloud API (>20MB)</b>\n\n"
                    "Telegram's standard Cloud API limits bot file downloads to <b>20 MB</b>.\n"
                    "To ingest files up to <b>2,000 MB (2 GB)</b>, the bot must be connected to the <b>Local Telegram Bot API Server</b> (<code>http://127.0.0.1:8081</code>) running with <code>local_mode=True</code>."
                )
            else:
                msg = f"❌ <b>File Transfer Error:</b> <code>{err_str}</code>"
            await status_msg.edit_text(msg, parse_mode=ParseMode.HTML)
    finally:
        done_event.set()
        if not monitor_task.done():
            monitor_task.cancel()
        await task_manager.unregister_task(task.task_id)
