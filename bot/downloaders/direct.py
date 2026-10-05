import os
import shutil
import time
import httpx
from telegram.constants import ParseMode
from bot.config import MOVIES_DIR, MUSIC_DIR
from bot.core.task_manager import task_manager, DownloadTask
from bot.utils.formatters import (
    build_status_message,
    get_readable_file_size,
    get_readable_time,
    sanitize_filename
)
from bot.logger import logger

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.m4a', '.opus', '.ogg')

async def run_direct_download(url: str, filename: str, task: DownloadTask):
    """
    Asynchronously streams direct file URLs in chunks with live MLTB status updates and cancellation.
    """
    clean_filename = sanitize_filename(filename)
    # Determine destination folder
    _, ext = os.path.splitext(clean_filename.lower())
    dest_dir = MUSIC_DIR if ext in AUDIO_EXTENSIONS else MOVIES_DIR
    os.makedirs(dest_dir, exist_ok=True)

    final_filepath = os.path.join(dest_dir, clean_filename)
    temp_filepath = os.path.join(dest_dir, f".tmp_{task.task_id}_{clean_filename}")
    task.temp_filepath = temp_filepath

    downloaded = 0
    total_bytes = None
    start_time = task.start_time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=None, headers=headers) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    await task.message.edit_text(
                        f"❌ <b>Download Failed:</b> HTTP {resp.status_code} ({resp.reason_phrase})",
                        parse_mode=ParseMode.HTML
                    )
                    return

                content_len = resp.headers.get("content-length")
                if content_len and content_len.isdigit():
                    total_bytes = int(content_len)

                # Stream and save to disk
                with open(temp_filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):  # 1 MB chunk
                        if task.is_cancelled:
                            task.cancel()
                            await task.message.edit_text("❌ <b>Download Cancelled by User.</b>", parse_mode=ParseMode.HTML)
                            return

                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        speed = downloaded / (now - start_time) if (now - start_time) > 0 else 0

                        status_text = build_status_message(
                            name=clean_filename,
                            status="Downloading",
                            downloaded_bytes=downloaded,
                            total_bytes=total_bytes,
                            speed=speed,
                            start_time=start_time,
                            engine=task.engine,
                            user_name=task.user_name,
                            user_id=task.user_id
                        )
                        await task_manager.safe_edit_status(task, status_text)

        # Download complete, rename temp file to final destination
        if os.path.exists(temp_filepath):
            # If target already exists, resolve duplicate
            if os.path.exists(final_filepath):
                base, ext_ = os.path.splitext(clean_filename)
                final_filepath = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext_}")

            shutil.move(temp_filepath, final_filepath)
            task.temp_filepath = None

            elapsed_str = get_readable_time(int(time.time() - start_time))
            size_str = get_readable_file_size(downloaded)

            await task.message.edit_text(
                f"✅ <b>Download Completed!</b>\n\n"
                f"<b>┌ Name:</b> <code>{os.path.basename(final_filepath)}</code>\n"
                f"<b>├ Size:</b> {size_str}\n"
                f"<b>├ Time:</b> {elapsed_str}\n"
                f"<b>└ Saved to:</b> <code>{final_filepath}</code>",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Direct download completed: {final_filepath} ({size_str})")

    except Exception as e:
        logger.error(f"Direct download error on task {task.task_id}: {e}", exc_info=True)
        if not task.is_cancelled:
            await task.message.edit_text(
                f"❌ <b>Download Error:</b> <code>{str(e)}</code>",
                parse_mode=ParseMode.HTML
            )
    finally:
        # Cleanup
        if task.temp_filepath and os.path.exists(task.temp_filepath):
            try:
                os.remove(task.temp_filepath)
            except Exception:
                pass
        await task_manager.unregister_task(task.task_id)
