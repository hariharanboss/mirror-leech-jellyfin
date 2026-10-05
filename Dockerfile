FROM python:3.13-slim

# Prevent Python from writing .pyc and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies: ffmpeg (for media processing), nodejs (yt-dlp extractors), wget, procps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    wget \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code
COPY bot/ ./bot/

# Set working directory to execute bot package
CMD ["python", "-m", "bot.main"]
