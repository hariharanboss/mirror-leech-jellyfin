import os
import time
import platform
import psutil
from bot.utils.formatters import get_readable_file_size, get_readable_time

BOT_START_TIME = time.time()

def get_system_stats(movies_dir: str = "/movies", music_dir: str = "/music") -> str:
    """
    Retrieves full system hardware and resource usage statistics in MLTB format.
    Reports CPU, Memory, Storage for media partitions, Uptime, and Network I/O.
    """
    # 1. Uptimes
    bot_uptime_sec = int(time.time() - BOT_START_TIME)
    bot_uptime_str = get_readable_time(bot_uptime_sec)

    try:
        boot_time = psutil.boot_time()
        os_uptime_sec = int(time.time() - boot_time)
        os_uptime_str = get_readable_time(os_uptime_sec)
    except Exception:
        os_uptime_str = "Unavailable"

    # 2. CPU Metrics
    cpu_percent = psutil.cpu_percent(interval=0.3)
    cpu_cores = psutil.cpu_count(logical=True)
    cpu_freq = psutil.cpu_freq()
    freq_str = f" @ {cpu_freq.current / 1000:.2f} GHz" if cpu_freq else ""

    # 3. Memory Metrics
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # 4. Storage Metrics (Movies and Root)
    target_path = movies_dir if os.path.exists(movies_dir) else "/"
    disk = psutil.disk_usage(target_path)

    # 5. Network Traffic
    net = psutil.net_io_counters()

    # 6. OS & Python Info
    os_name = f"{platform.system()} {platform.release()}"

    return (
        f"📊 <b><u>Dell Server Statistics</u></b>\n\n"
        f"<b>• OS:</b> <code>{os_name}</code>\n"
        f"<b>• Bot Uptime:</b> <code>{bot_uptime_str}</code>\n"
        f"<b>• OS Uptime:</b> <code>{os_uptime_str}</code>\n\n"
        f"<b>• CPU Usage:</b> <code>{cpu_percent}%</code> ({cpu_cores} Cores{freq_str})\n"
        f"<b>• RAM Usage:</b> <code>{get_readable_file_size(ram.used)} / {get_readable_file_size(ram.total)} ({ram.percent}%)</code>\n"
        f"<b>• Swap Usage:</b> <code>{get_readable_file_size(swap.used)} / {get_readable_file_size(swap.total)} ({swap.percent}%)</code>\n\n"
        f"<b>• Storage ({target_path}):</b>\n"
        f"<b>  ├ Used:</b> <code>{get_readable_file_size(disk.used)} / {get_readable_file_size(disk.total)} ({disk.percent}%)</code>\n"
        f"<b>  └ Free:</b> <code>{get_readable_file_size(disk.free)}</code>\n\n"
        f"<b>• Network I/O:</b>\n"
        f"<b>  ├ Sent:</b> <code>{get_readable_file_size(net.bytes_sent)}</code>\n"
        f"<b>  └ Recv:</b> <code>{get_readable_file_size(net.bytes_recv)}</code>"
    )
