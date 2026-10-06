import os
import re
import time
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
    - Returns type='media' ONLY for dedicated video streaming platforms (YouTube, Instagram, etc.)
    - Returns type='direct' for direct file downloads, Cloudflare workers, index links, or raw files
    """
    url = url.strip()

    # 1. Immediate match for known streaming video sites (YouTube, Insta, TikTok, etc.)
    if MEDIA_SITES_REGEX.match(url):
        return {
            "type": "media",
            "url": url,
            "filename": None,
            "size": None
        }

    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path.lower()

    # 2. Check if URL path has a known media file extension directly
    for ext in DIRECT_EXTENSIONS:
        if clean_path.endswith(ext):
            filename = os.path.basename(parsed.path) or "downloaded_media"
            return {
                "type": "direct",
                "url": url,
                "filename": urllib.parse.unquote(filename),
                "size": None
            }

    # 3. Check if query parameters contain a filename (e.g. ?file=video.mp4 or ?name=movie.mkv)
    query_params = urllib.parse.parse_qs(parsed.query)
    for q_key in ("file", "filename", "name", "title", "fn"):
        if q_key in query_params and query_params[q_key]:
            val = query_params[q_key][0]
            if any(val.lower().endswith(ext) for ext in DIRECT_EXTENSIONS):
                return {
                    "type": "direct",
                    "url": url,
                    "filename": urllib.parse.unquote(val),
                    "size": None
                }

    # 4. HTTP probe to inspect headers (detects Cloudflare workers, File-to-Link bots, CDNs)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    filename = None
    size_bytes = None
    detected_url = url

    try:
        transport = httpx.AsyncHTTPTransport(retries=2)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=8.0, headers=headers) as client:
            resp = await client.head(url)

            # If server blocks HEAD request, try a 1-byte GET Range request
            if resp.status_code in (403, 404, 405):
                resp = await client.get(url, headers={**headers, "Range": "bytes=0-0"})

            detected_url = str(resp.url)
            content_length = resp.headers.get("content-length")
            content_disp = resp.headers.get("content-disposition", "")
            content_range = resp.headers.get("content-range", "")

            # Extract filename from Content-Disposition if available
            if "filename=" in content_disp:
                match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', content_disp, re.IGNORECASE)
                if match:
                    filename = match.group(1).strip()

            # Determine file size
            if content_length and content_length.isdigit():
                size_bytes = int(content_length)
            elif content_range and "/" in content_range:
                tot_str = content_range.split("/")[-1]
                if tot_str.isdigit():
                    size_bytes = int(tot_str)

    except Exception as e:
        logger.debug(f"URL probe failed for {url}: {e}")

    # 5. Clean up filename or generate fallback
    if not filename:
        raw_basename = os.path.basename(parsed.path)
        if raw_basename and not raw_basename.isdigit():
            filename = urllib.parse.unquote(raw_basename)
        else:
            filename = f"downloaded_media_{int(time.time())}"

    # Ensure default fallback is DIRECT for any non-YouTube URL
    return {
        "type": "direct",
        "url": detected_url,
        "filename": filename,
        "size": size_bytes
    }
