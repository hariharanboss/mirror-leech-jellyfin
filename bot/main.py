import sys
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from bot.config import BOT_TOKEN, BOT_API_URL
from bot.logger import logger
from bot.handlers.commands import (
    start_command,
    help_command,
    stats_command,
    ping_command
)
from bot.handlers.links import link_message_handler
from bot.handlers.files import file_message_handler
from bot.handlers.callbacks import callback_query_handler

def create_application() -> Application:
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set! Exiting.")
        sys.exit(1)

    from telegram.request import HTTPXRequest

    # Set generous timeouts (30 minutes) to allow the Local Bot API to download large files (up to 2GB)
    request_pool = HTTPXRequest(
        connection_pool_size=16,
        read_timeout=1800.0,
        write_timeout=1800.0,
        connect_timeout=60.0,
        pool_timeout=60.0
    )

    builder = Application.builder().token(BOT_TOKEN).request(request_pool)

    # Configure Local Telegram Bot API if configured
    if BOT_API_URL and "api.telegram.org" not in BOT_API_URL:
        logger.info(f"Connecting to Local Telegram Bot API at: {BOT_API_URL}")
        builder = (
            builder
            .base_url(f"{BOT_API_URL}/bot")
            .base_file_url(f"{BOT_API_URL}/file/bot")
            .local_mode(True)
        )
    else:
        logger.info("Using standard Telegram Cloud API")

    app = builder.build()

    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("server", stats_command))
    app.add_handler(CommandHandler("ping", ping_command))

    # Register Link Detection Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_message_handler))

    # Register Media File Handlers
    media_filter = (
        filters.Document.ALL
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
    )
    app.add_handler(MessageHandler(media_filter, file_message_handler))

    # Register Callback Query Handlers (Buttons)
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    return app

def main():
    logger.info("Starting Telegram Media Bot...")
    app = create_application()
    logger.info("Bot application built successfully. Listening for updates...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
