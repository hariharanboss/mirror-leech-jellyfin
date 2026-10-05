import os
import re
import urllib.parse
from typing import Dict, Any
import httpx
from bot.logger import logger

# Regex for streaming/video platforms that should go to yt-dlp quality selection
MEDIA_SITES_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com|'
    r'instagram\.com|tiktok\.com|twitter\.com|x\.com|'
    r'reddit\.com|facebook\.com|fb\.watch|vimeo\.com|twitch\.tv|dailymotion\.com|soundcloud\.com)/.+',
    re.IGNORECASE
)

# Common media and archive file extensions
DIRECT_EXTENSIONS = (
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v',
    '.mp3', '.flac', '.wav', '.aac', '.m4a', '.opus', '.ogg',
    '.zip', '.rar', '.tar', '.gz', '.7z', '.iso', '.bin'
)

def is_url(text: str) -> bool:
    """Validates if the provided text string is an HTTP/HTTPS URL."""
    try:
        parsed = urllib.parse.urlparse(text.strip())
        return parsed.scheme in ('http', 'https', 'ftp') and bool(parsed.netloc)
    except Exception:
        return False

async def detect_url_type(url: str) -> Dict[str, Any]:
    """
    Analyzes an incoming URL:
    - Returns type='media' for video streaming platforms (YouTube, Instagram, etc.)
    - Returns type='direct' for direct stream files, Cloudflare workers, or index links
    """
    url = url.strip()

    # 1. Immediate match for known streaming sites (YouTube, X, Insta, etc.)
    if MEDIA_SITES_REGEX.match(url):
        return {
            "type": "media",
            "url": url,
            "filename": None,
            "size": None
        }

    # 2. Check URL path extension directly
    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path.lower()
    for ext in DIRECT_EXTENSIONS:
        if clean_path.endswith(ext):
            filename = os.path.basename(parsed.path) or "downloaded_media"
            return {
                "type": "direct",
                "url": url,
                "filename": urllib.parse.unquote(filename),
                "size": None
            }

    # 3. HTTP HEAD probe (detects Cloudflare workers, direct CDNs, stream servers)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=7.0, headers=headers) as client:
            resp = await client.head(url)
            # If server forbids HEAD (common on some CDNs), request byte 0 with GET Range
            if resp.status_code in (403, 405):
                resp = await client.get(url, headers={"Range": "bytes=0-0"})

            content_type = resp.headers.get("content-type", "").lower()
            content_length = resp.headers.get("content-length")
            content_disp = resp.headers.get("content-disposition", "")

            # Extract filename from Content-Disposition if present
            filename = None
            if "filename=" in content_disp:
                match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', content_disp)
                if match:
                    filename = match.group(1)

            if not filename:
                filename = os.path.basename(parsed.path) or "downloaded_stream"
            filename = urllib.parse.unquote(filename)

            size_bytes = int(content_length) if content_length and content_length.isdigit() else None

            # Detect direct file indicators
            is_direct_stream = (
                any(content_type.startswith(prefix) for prefix in ("video/", "audio/", "application/octet-stream", "application/x-"))
                or "attachment" in content_disp
                or any(clean_path.endswith(ext) for ext in DIRECT_EXTENSIONS)
            )

            if is_direct_stream:
                return {
                    "type": "direct",
                    "url": str(resp.url),
                    "filename": filename,
                    "size": size_bytes
                }
    except Exception as e:
        logger.debug(f"URL probe failed for {url}: {e}")

    # Fallback default: Let yt-dlp attempt extraction
    return {
        "type": "media",
        "url": url,
        "filename": None,
        "size": None
    }
