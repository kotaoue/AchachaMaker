"""Runtime environment setup for application startup."""

from __future__ import annotations

import os


def configure_runtime_environment() -> None:
    """Apply startup-time environment configuration for the app."""
    _configure_qt_logging()


def _configure_qt_logging() -> None:
    """Suppress noisy Qt FFmpeg backend warnings in terminal output."""
    _append_qt_logging_rule("qt.multimedia.ffmpeg.warning=false")


def _append_qt_logging_rule(rule: str) -> None:
    """Append a Qt logging rule to QT_LOGGING_RULES without duplicates."""
    existing = os.environ.get("QT_LOGGING_RULES", "")
    if rule in existing:
        return
    os.environ["QT_LOGGING_RULES"] = f"{existing};{rule}" if existing else rule
