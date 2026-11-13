"""Logging configuration and third-party warning suppression helpers for Coddy."""

import logging


class _SuppressNonTextPartsFilter(logging.Filter):
    """Filter that suppresses harmless google_genai warnings when accessing .text on responses with non-text parts."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "there are non-text parts in the response" not in record.getMessage()


def configure_logging() -> None:
    """Configures logging for Coddy, silencing noisy third-party SDK warnings."""
    filter_instance = _SuppressNonTextPartsFilter()
    for logger_name in ("google_genai", "google_genai.types"):
        log = logging.getLogger(logger_name)
        log.addFilter(filter_instance)
        log.setLevel(logging.ERROR)
