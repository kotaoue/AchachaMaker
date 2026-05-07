"""Application configuration and platform-specific settings."""

import platform
from PyQt6.QtGui import QFont


def get_font(family_size_tuple: tuple[str, int] = ("default", 9)) -> QFont:
    """Return a QFont with platform-appropriate font family.

    Args:
        family_size_tuple: Tuple of (font_style, size). font_style can be:
            - "default": Standard UI font for the platform
            - "monospace": Monospace font for code/numbers

    Returns:
        QFont instance configured for the current OS.
    """
    font_style, size = family_size_tuple
    system = platform.system()

    # Font families by OS and style
    fonts = {
        ("Darwin", "monospace"): "Menlo",
        ("Darwin", "default"): "Hiragino Sans",
        ("Windows", "monospace"): "Courier New",
        ("Windows", "default"): "Yu Gothic",
        ("Linux", "monospace"): "Noto Mono",
        ("Linux", "default"): "Noto Sans CJK JP",
    }

    key = (system, font_style)
    font_family = fonts.get(key, fonts.get(("Linux", font_style)))  # Default to Linux fallback
    return QFont(font_family, size)


# Preset font configurations for common use cases
FONT_LABEL = get_font(("default", 9))
FONT_EXPORT_BUTTON = get_font(("default", 12))
FONT_MONOSPACE_SMALL = get_font(("monospace", 9))


def get_system_name() -> str:
    """Return the current OS name."""
    return platform.system()
