import socket
import ssl
import sys

# 1. Force IPv4 resolution to bypass broken IPv6 routing on college / enterprise networks
_orig_getaddrinfo = socket.getaddrinfo

def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    if family == socket.AF_UNSPEC:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _getaddrinfo_ipv4

# 2. Relax strict SSL/TLS validation flags (VERIFY_X509_STRICT, legacy renegotiation)
# preventing httpcore.ConnectError caused by enterprise firewall inspection / CDN edge renegotiation
_orig_create_default_context = ssl.create_default_context

def _relaxed_create_default_context(*args, **kwargs):
    ctx = _orig_create_default_context(*args, **kwargs)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    return ctx

ssl.create_default_context = _relaxed_create_default_context


from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from bot.config import BOT_TOKEN, BOT_API_URL
from bot.logger import logger
from bot.handlers.commands import (
    start_command,
    help_command,
    stats_command,
    ping_command,
    cancel_command
)
from bot.handlers.links import link_message_handler
from bot.handlers.files import file_message_handler
from bot.handlers.callbacks import callback_query_handler

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by network drops or unhandled exceptions."""
    logger.error(f"Uncaught exception while processing update: {context.error}")

def create_application() -> Application:
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set! Exiting.")
        sys.exit(1)

    from telegram.request import HTTPXRequest

    # Set generous timeouts (30 minutes) and HTTP/1.1 for rock-solid stability
    request_pool = HTTPXRequest(
        connection_pool_size=16,
        read_timeout=1800.0,
        write_timeout=1800.0,
        connect_timeout=60.0,
        pool_timeout=60.0,
        http_version="1.1"
    )

    builder = Application.builder().token(BOT_TOKEN).request(request_pool)

    # Configure Bot API endpoint (Local Docker API or Cloudflare Reverse Proxy)
    if BOT_API_URL and "api.telegram.org" not in BOT_API_URL:
        is_local_server = any(h in BOT_API_URL for h in ("telegram-bot-api", "localhost", "127.0.0.1"))
        logger.info(f"Connecting to Bot API at: {BOT_API_URL} (local_mode={is_local_server})")
        builder = (
            builder
            .base_url(f"{BOT_API_URL}/bot")
            .base_file_url(f"{BOT_API_URL}/file/bot")
            .local_mode(is_local_server)
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
    app.add_handler(CommandHandler("cancel", cancel_command))

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

    # Register Global Error Handler
    app.add_error_handler(error_handler)

    return app

def main():
    logger.info("Starting Telegram Media Bot...")
    app = create_application()
    logger.info("Bot application built successfully. Listening for updates...")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
