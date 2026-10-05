import logging
import re
import sys

class SensitiveDataFilter(logging.Filter):
    """
    Scrubs Telegram bot tokens and secrets from log messages.
    Prevents token leakage in docker logs and terminal outputs.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Redact /bot<token>/ in URLs
            record.msg = re.sub(r'/bot[0-9]+:[a-zA-Z0-9_-]+/', '/bot[REDACTED_TOKEN]/', record.msg)
            # Redact standalone tokens
            record.msg = re.sub(r'\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b', '[REDACTED_TOKEN]', record.msg)
        return True

def setup_logger():
    # Base logging format
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s -> %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # Attach sensitive data scrubber to all handlers
    scrubber = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(scrubber)

    # Suppress verbose HTTP connection logs from chatty libraries
    for noisy_module in ("httpx", "httpcore", "urllib3", "telegram.ext.ExtBot"):
        logging.getLogger(noisy_module).setLevel(logging.WARNING)

    return logging.getLogger("MediaBot")

logger = setup_logger()
