import asyncio
import os
import shutil
import time
import httpx
from telegram.constants import ParseMode
from bot.config import MOVIES_DIR, MUSIC_DIR, BOT_API_URL
from bot.core.task_manager import task_manager, DownloadTask
from bot.utils.formatters import (
    build_status_message,
    get_readable_file_size,
    get_readable_time,
    sanitize_filename
)
from bot.logger import logger

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.m4a', '.opus', '.ogg')
NUM_PARALLEL_CHUNKS = 16

async def run_direct_download(url: str, filename: str, task: DownloadTask):
    """
    Downloads direct files with high-speed multi-connection parallel chunking (up to 16x streams),
    falling back seamlessly to single-stream chunking if range requests are not supported.
    """
    clean_filename = sanitize_filename(filename)
    _, ext = os.path.splitext(clean_filename.lower())
    dest_dir = MUSIC_DIR if ext in AUDIO_EXTENSIONS else MOVIES_DIR
    os.makedirs(dest_dir, exist_ok=True)

    final_filepath = os.path.join(dest_dir, clean_filename)
    temp_filepath = os.path.join(dest_dir, f".tmp_{task.task_id}_{clean_filename}")
    task.temp_filepath = temp_filepath

    start_time = task.start_time

    # If URL points to Telegram file server and custom Bot API proxy is configured, rewrite host
    download_url = url
    if BOT_API_URL and "api.telegram.org" in download_url:
        download_url = download_url.replace("https://api.telegram.org", BOT_API_URL.rstrip("/"))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    transport = httpx.AsyncHTTPTransport(retries=3)

    try:
        # 1. Probe for Content-Length and Range support
        total_bytes = None
        supports_ranges = False

        async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=15.0, headers=headers) as probe_client:
            try:
                head_resp = await probe_client.head(download_url)
                if head_resp.status_code == 200:
                    cl = head_resp.headers.get("content-length")
                    if cl and cl.isdigit():
                        total_bytes = int(cl)
                    ar = head_resp.headers.get("accept-ranges", "").lower()
                    if ar == "bytes":
                        supports_ranges = True
            except Exception:
                pass

            if not total_bytes or not supports_ranges:
                try:
                    range_probe = await probe_client.get(download_url, headers={**headers, "Range": "bytes=0-0"})
                    cr = range_probe.headers.get("content-range")
                    if cr and "/" in cr:
                        t_str = cr.split("/")[-1]
                        if t_str.isdigit():
                            total_bytes = int(t_str)
                            supports_ranges = True
                except Exception:
                    pass

        # 2. Decide between Multi-Stream Parallel and Single-Stream
        # Multi-stream is activated if server supports ranges and file >= 5MB
        if supports_ranges and total_bytes and total_bytes >= 5 * 1024 * 1024:
            num_workers = min(NUM_PARALLEL_CHUNKS, max(2, total_bytes // (1024 * 1024)))
            chunk_size = total_bytes // num_workers

            ranges = []
            for i in range(num_workers):
                s = i * chunk_size
                e = total_bytes - 1 if i == num_workers - 1 else (i + 1) * chunk_size - 1
                ranges.append((s, e))

            # Pre-allocate target file
            with open(temp_filepath, "wb") as f:
                f.truncate(total_bytes)

            file_obj = open(temp_filepath, "r+b")
            file_lock = asyncio.Lock()
            downloaded = 0
            last_edit_time = 0

            async def chunk_worker(start_byte: int, end_byte: int):
                nonlocal downloaded, last_edit_time
                w_headers = {**headers, "Range": f"bytes={start_byte}-{end_byte}"}
                current_pos = start_byte

                async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=60.0, headers=w_headers) as w_client:
                    async with w_client.stream("GET", download_url) as w_resp:
                        if w_resp.status_code not in (200, 206):
                            raise RuntimeError(f"HTTP {w_resp.status_code} on byte range {start_byte}-{end_byte}")

                        async for chunk in w_resp.aiter_bytes(chunk_size=256 * 1024):
                            if task.is_cancelled:
                                return

                            async with file_lock:
                                file_obj.seek(current_pos)
                                file_obj.write(chunk)

                            c_len = len(chunk)
                            current_pos += c_len
                            downloaded += c_len

                            now = time.time()
                            if now - last_edit_time >= 2.5:
                                last_edit_time = now
                                speed = downloaded / (now - start_time) if (now - start_time) > 0 else 0
                                status_text = build_status_message(
                                    name=clean_filename,
                                    status=f"Downloading ({num_workers}x)",
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_bytes,
                                    speed=speed,
                                    start_time=start_time,
                                    engine=f"Direct-{num_workers}x",
                                    task_id=task.task_id,
                                    user_name=task.user_name,
                                    user_id=task.user_id
                                )
                                await task_manager.safe_edit_status(task, status_text)

            try:
                await asyncio.gather(*[chunk_worker(s, e) for s, e in ranges])
            finally:
                file_obj.close()

            if task.is_cancelled:
                task.cancel()
                await task.message.edit_text("❌ <b>Download Cancelled by User.</b>", parse_mode=ParseMode.HTML)
                return

        else:
            # Single-Stream Fallback (for servers that reject range requests)
            downloaded = 0
            async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=None, headers=headers) as client:
                async with client.stream("GET", download_url) as resp:
                    if resp.status_code >= 400:
                        await task.message.edit_text(
                            f"❌ <b>Download Failed:</b> HTTP {resp.status_code} ({resp.reason_phrase})",
                            parse_mode=ParseMode.HTML
                        )
                        return

                    cl = resp.headers.get("content-length")
                    if cl and cl.isdigit():
                        total_bytes = int(cl)

                    with open(temp_filepath, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
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
                                task_id=task.task_id,
                                user_name=task.user_name,
                                user_id=task.user_id
                            )
                            await task_manager.safe_edit_status(task, status_text)

        # Download complete, rename temp file to final destination
        if os.path.exists(temp_filepath):
            if os.path.exists(final_filepath):
                base, ext_ = os.path.splitext(clean_filename)
                final_filepath = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext_}")

            shutil.move(temp_filepath, final_filepath)
            task.temp_filepath = None

            elapsed_str = get_readable_time(int(time.time() - start_time))
            final_size = os.path.getsize(final_filepath)
            size_str = get_readable_file_size(final_size)

            await task.message.edit_text(
                f"✅ <b>Download Completed!</b>\n\n"
                f"<b>┌ Name:</b> <code>{os.path.basename(final_filepath)}</code>\n"
                f"<b>├ Size:</b> {size_str}\n"
                f"<b>├ Time:</b> {elapsed_str}\n"
                f"<b>└ Saved to:</b> <code>{final_filepath}</code>",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Direct download completed: {final_filepath} ({size_str})")

    except httpx.HTTPError as e:
        logger.error(f"Direct download network error on task {task.task_id}: {e}")
        if not task.is_cancelled:
            await task.message.edit_text(
                f"❌ <b>Download Failed (Network Error):</b>\n<code>{type(e).__name__}: {str(e)}</code>",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Direct download error on task {task.task_id}: {e}", exc_info=True)
        if not task.is_cancelled:
            await task.message.edit_text(
                f"❌ <b>Download Error:</b>\n<code>{str(e)}</code>",
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
