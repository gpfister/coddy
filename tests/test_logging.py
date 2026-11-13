"""Unit tests for Coddy logging helpers and third-party warning suppression."""

import logging

from app.coddy.helpers.logging_helpers import _SuppressNonTextPartsFilter, configure_logging


def test_suppress_non_text_parts_filter():
    """Verify that _SuppressNonTextPartsFilter blocks warnings about non-text parts."""
    log_filter = _SuppressNonTextPartsFilter()

    record_to_drop = logging.LogRecord(
        name="google_genai.types",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Warning: there are non-text parts in the response: ['function_call'], returning concatenated text result from text parts.",
        args=(),
        exc_info=None,
    )
    assert not log_filter.filter(record_to_drop)

    record_to_keep = logging.LogRecord(
        name="google_genai.types",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Some other legitimate warning message",
        args=(),
        exc_info=None,
    )
    assert log_filter.filter(record_to_keep)


def test_configure_logging():
    """Verify configure_logging attaches filter and sets ERROR level on target loggers."""
    configure_logging()
    for name in ("google_genai", "google_genai.types"):
        target_logger = logging.getLogger(name)
        assert target_logger.level == logging.ERROR
        assert any(isinstance(f, _SuppressNonTextPartsFilter) for f in target_logger.filters)
