# 🤖 Telegram Media Bot (AIBBOT)

A high-performance, containerized Telegram bot designed to download media, streams, and files directly to a local server and ingest them automatically into **Jellyfin**.

Built with inspiration from **MLTB (`mirror-leech-telegram-bot`)** for professional progress rendering, real-time server metrics, task cancellation, and smart link classification.

---

## 🌟 Key Features

- **🚀 Local Telegram Bot API**: Connects to a local instance of `telegram-bot-api` with `TELEGRAM_LOCAL=1`. Allows direct zero-copy file ingest for files up to **2 GB**.
- **🧠 Smart URL Engine (MLTB Style)**:
  - **YouTube & Social Platforms:** Quality selection dialog (`1080p`, `720p`, `480p`, `MP3`).
  - **Direct Links & Cloudflare Workers (`f2l.harisgarage.workers.dev`):** Probes headers with `HEAD` / `GET Range`, detects file size & filename, and triggers direct streaming with no unnecessary quality prompts.
- **📊 MLTB Status & Progress UI**:
  - Live ASCII progress bars (`[▓▓▓▓▓░░░░░] 52.0%`).
  - Monospaced metadata: Processed bytes, real-time speed, ETA, elapsed time, engine type, user attribution.
  - Rate-limited message editing (every 3 seconds) preventing Telegram `FloodWait` (429).
- **🛑 Task Cancellation**: Every download has a `[ ❌ Cancel ]` button. Kills the entire process group for `yt-dlp` / `ffmpeg` and cleans up partial temp files.
- **📈 Server Hardware Stats (`/stats` & `/server`)**: Complete resource monitoring via `psutil`: CPU usage and cores, RAM & Swap consumption, Jellyfin storage breakdown, network I/O, bot and OS uptime.
- **🔐 Token Redaction Filter**: Custom logging filter guarantees bot tokens are redacted from logs and never leak to `docker logs` or stdout.

---

## 🏗️ Architecture

```text
                    Telegram Cloud Servers
                              │
                              ▼
                 ┌──────────────────────────┐
                 │  Local Telegram Bot API  │ (Port 8081)
                 │    aiogram/telegram-bot  │
                 └────────────┬─────────────┘
                              │
                   Shared Volume (/var/lib)
                              │
                              ▼
                     ┌──────────────────┐
                     │   AIBBOT (App)   │
                     │  python 3.13 slim│
                     └────────┬─────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
       Direct HTTP Stream             yt-dlp / ffmpeg
               │                             │
               └──────────────┬──────────────┘
                              ▼
                       Jellyfin Server
                    /movies   │   /music
```

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/telegram-media-bot.git ~/docker
cd ~/docker
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
nano .env
```

Set your configuration:
```env
BOT_TOKEN=your_telegram_bot_token_from_botfather
TELEGRAM_API_ID=your_api_id_from_my_telegram_org
TELEGRAM_API_HASH=your_api_hash_from_my_telegram_org

BOT_API_URL=http://telegram-bot-api:8081
MOVIES_DIR=/movies
MUSIC_DIR=/music
ALLOWED_USERS=
```

### 3. Start the Docker Stack
```bash
docker compose up -d --build
```

To inspect logs without risk of token leaks:
```bash
docker compose logs -f bot
```

---

## 💬 Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and feature overview |
| `/help` | Detailed usage guide |
| `/stats` or `/server` | Live Dell server hardware statistics (CPU, RAM, Disk, Net I/O) |
| `/ping` | Test bot response latency |

---

## 📂 Media Organization

| Type | Destination | Notes |
|---|---|---|
| Video files (`.mkv`, `.mp4`, `.avi`, `.mov`) | `/movies` | Automatically indexed by Jellyfin |
| Documents / Archives (`.zip`, `.iso`, `.tar`) | `/movies` | Preserves original filename |
| Audio files (`.mp3`, `.flac`, `.wav`, Voice) | `/music` | yt-dlp MP3 conversions and voice notes |

---

## 🛠️ Stack Components

- **Runtime:** Python 3.13 Slim
- **Framework:** `python-telegram-bot` (v20+)
- **Engines:** `yt-dlp`, `ffmpeg`, `httpx` (async HTTP streams)
- **Monitoring:** `psutil`
- **Containerization:** Docker Compose
