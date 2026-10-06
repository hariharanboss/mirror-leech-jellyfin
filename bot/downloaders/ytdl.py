import asyncio
import os
import re
import time
from typing import Optional
from telegram.constants import ParseMode
from bot.config import MOVIES_DIR, MUSIC_DIR
from bot.core.task_manager import task_manager, DownloadTask
from bot.utils.formatters import (
    build_status_message,
    get_readable_time,
    get_readable_file_size
)
from bot.logger import logger

# Regex to parse standard yt-dlp stdout progress lines
YTDL_PROGRESS_REGEX = re.compile(
    r'\[download\]\s+(\d+\.?\d*)%\s+of\s+~?(\d+\.?\d*)([KMGTP]?i?B)\s+at\s+~?(\d+\.?\d*)([KMGTP]?i?B/s)\s+ETA\s+(\d{2}:\d{2}(?::\d{2})?)'
)

UNIT_MULTIPLIERS = {
    'B': 1,
    'KiB': 1024,
    'KB': 1000,
    'MiB': 1024**2,
    'MB': 1000**2,
    'GiB': 1024**3,
    'GB': 1000**3,
    'TiB': 1024**4,
    'TB': 1000**4
}

def parse_size_to_bytes(amount_str: str, unit_str: str) -> int:
    try:
        val = float(amount_str)
        multiplier = UNIT_MULTIPLIERS.get(unit_str.replace("/s", ""), 1)
        return int(val * multiplier)
    except Exception:
        return 0

QUALITY_MAP = {
    "best": {
        "format": "bestvideo+bestaudio/best",
        "audio_only": False,
        "label": "Best Available"
    },
    "2160": {
        "format": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
        "audio_only": False,
        "label": "4K (2160p)"
    },
    "1440": {
        "format": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
        "audio_only": False,
        "label": "2K (1440p)"
    },
    "1080": {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "audio_only": False,
        "label": "1080p (FHD)"
    },
    "720": {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "audio_only": False,
        "label": "720p (HD)"
    },
    "480": {
        "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "audio_only": False,
        "label": "480p (SD)"
    },
    "360": {
        "format": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        "audio_only": False,
        "label": "360p"
    },
    "mp3": {
        "format": "bestaudio/best",
        "audio_only": True,
        "label": "MP3 Audio"
    }
}

async def run_ytdl_download(url: str, quality_key: str, task: DownloadTask, custom_name: Optional[str] = None):
    """
    Spawns yt-dlp as an async subprocess with process group isolation,
    parses real-time stdout progress, and renders live MLTB status.
    """
    cfg = QUALITY_MAP.get(quality_key, QUALITY_MAP["720"])
    is_audio = cfg["audio_only"]
    dest_dir = MUSIC_DIR if is_audio else MOVIES_DIR
    os.makedirs(dest_dir, exist_ok=True)

    if custom_name:
        output_template = os.path.join(dest_dir, f"{custom_name}.%(ext)s")
    else:
        output_template = os.path.join(dest_dir, "%(title)s [%(id)s].%(ext)s")

    cmd = [
        "yt-dlp",
        "--newline",
        "--no-playlist",
        "--progress",
        "--concurrent-fragments", "16",
        "--buffer-size", "16M",
        "--retries", "10",
        "--fragment-retries", "10",
        "--format", cfg["format"],
        "-o", output_template,
    ]

    if is_audio:
        cmd.extend(["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"])

    cmd.append(url)

    logger.info(f"Starting yt-dlp task {task.task_id} with format {quality_key}")
    start_time = task.start_time

    try:
        # Start subprocess in its own process group for clean group termination on cancel
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True  # Enables process group kill (setsid)
        )
        task.process = process

        downloaded_bytes = 0
        total_bytes = 0
        speed_bytes = 0

        # Read output stream line by line
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if line.startswith("[download] Destination:"):
                dest_file = line.replace("[download] Destination:", "").strip()
                task.name = os.path.basename(dest_file)

            match = YTDL_PROGRESS_REGEX.search(line)
            if match:
                pct = float(match.group(1))
                tot_amount = match.group(2)
                tot_unit = match.group(3)
                spd_amount = match.group(4)
                spd_unit = match.group(5)

                total_bytes = parse_size_to_bytes(tot_amount, tot_unit)
                speed_bytes = parse_size_to_bytes(spd_amount, spd_unit)
                downloaded_bytes = int((pct / 100.0) * total_bytes)

                status_text = build_status_message(
                    name=task.name,
                    status="Downloading",
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes,
                    speed=speed_bytes,
                    start_time=start_time,
                    engine="yt-dlp",
                    task_id=task.task_id,
                    user_name=task.user_name,
                    user_id=task.user_id
                )
                await task_manager.safe_edit_status(task, status_text)

            elif "[Merger]" in line or "[ExtractAudio]" in line:
                await task_manager.safe_edit_status(
                    task,
                    f"<b>{task.name}</b>\n<b>Status:</b> <i>Processing & Converting Media...</i>",
                    force=True
                )

        await process.wait()

        if task.is_cancelled:
            await task.message.edit_text("❌ <b>Download Cancelled by User.</b>", parse_mode=ParseMode.HTML)
            return

        if process.returncode == 0:
            elapsed_str = get_readable_time(int(time.time() - start_time))
            size_str = get_readable_file_size(total_bytes) if total_bytes else "Complete"

            await task.message.edit_text(
                f"✅ <b>Download Completed!</b>\n\n"
                f"<b>┌ Name:</b> <code>{task.name}</code>\n"
                f"<b>├ Quality:</b> <code>{quality_key.upper()}</code>\n"
                f"<b>├ Size:</b> {size_str}\n"
                f"<b>├ Time:</b> {elapsed_str}\n"
                f"<b>└ Saved to:</b> <code>{dest_dir}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await task.message.edit_text(
                f"❌ <b>yt-dlp Failed with return code {process.returncode}</b>",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"yt-dlp error on task {task.task_id}: {e}", exc_info=True)
        if not task.is_cancelled:
            await task.message.edit_text(
                f"❌ <b>Download Error:</b> <code>{str(e)}</code>",
                parse_mode=ParseMode.HTML
            )
    finally:
        await task_manager.unregister_task(task.task_id)
