import re
import time
from typing import Optional

def get_readable_file_size(size_in_bytes: Optional[float]) -> str:
    """Formats raw byte counts to human-readable binary units (KiB, MiB, GiB)."""
    if size_in_bytes is None or size_in_bytes < 0:
        return "Unknown"
    size = float(size_in_bytes)
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PiB"

def get_readable_time(seconds: int) -> str:
    """Formats seconds into human-readable duration string."""
    if seconds < 0:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0:
        return f"{d}d {h}h {m}m {s}s"
    elif h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def get_progress_bar(percentage: float, length: int = 10) -> str:
    """Builds the classic MLTB progress bar: [▓▓▓▓░░░░░░]"""
    pct = max(0.0, min(100.0, percentage))
    filled = int(round(length * pct / 100))
    bar = "▓" * filled + "░" * (length - filled)
    return f"[{bar}]"

def sanitize_filename(filename: str) -> str:
    """Strips dangerous characters while preserving media extension."""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    return clean or "unnamed_media"

def build_status_message(
    name: str,
    status: str,
    downloaded_bytes: int,
    total_bytes: Optional[int],
    speed: float,
    start_time: float,
    task_id: str = "",
    user_name: str = "User",
    user_id: int = 0
) -> str:
    """
    Builds the signature MLTB progress status layout.
    Compatible with Telegram HTML parse mode.
    """
    elapsed_seconds = int(time.time() - start_time)
    elapsed_str = get_readable_time(elapsed_seconds)

    if total_bytes and total_bytes > 0:
        percent = min(100.0, (downloaded_bytes / total_bytes) * 100)
        p_bar = get_progress_bar(percent)
        processed_str = f"{get_readable_file_size(downloaded_bytes)} of {get_readable_file_size(total_bytes)}"
        
        if speed > 0:
            eta_seconds = int((total_bytes - downloaded_bytes) / speed)
            eta_str = get_readable_time(eta_seconds)
        else:
            eta_str = "Calculating..."
        percent_str = f"{percent:.1f}%"
    else:
        p_bar = "[░░░░░░░░░░]"
        percent_str = "0%"
        processed_str = f"{get_readable_file_size(downloaded_bytes)}"
        eta_str = "Unknown"

    speed_str = f"{get_readable_file_size(speed)}/s"

    msg = (
        f"<b>{name}</b>\n"
        f"<b>┌ </b><b>Status:</b> <i>{status}</i>\n"
        f"<b>├ </b><b>{p_bar}</b> {percent_str}\n"
        f"<b>├ </b><b>Processed:</b> {processed_str}\n"
        f"<b>├ </b><b>Speed:</b> {speed_str} | <b>ETA:</b> {eta_str}\n"
        f"<b>├ </b><b>Elapsed:</b> {elapsed_str}\n"
        f"<b>├ </b><b>Engine:</b> {engine}\n"
    )

    if task_id:
        msg += (
            f"<b>├ </b><b>Task ID:</b> <code>{task_id}</code>\n"
            f"<b>└ </b><b>To Cancel:</b> <code>/cancel {task_id}</code>"
        )
    else:
        msg += f"<b>└ </b><b>User:</b> <a href=\"tg://user?id={user_id}\">{user_name}</a> | <b>ID:</b> <code>{user_id}</code>"

    return msg
