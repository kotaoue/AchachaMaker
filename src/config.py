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

    if font_style == "monospace":
        if system == "Darwin":
            return QFont("Menlo", size)
        elif system == "Windows":
            return QFont("Courier New", size)
        else:  # Linux
            return QFont("Noto Mono", size)

    # Default (serif/sans-serif mix for better CJK support)
    if system == "Darwin":
        # macOS: Use Hiragino Sans for Japanese support
        return QFont("Hiragino Sans", size)
    elif system == "Windows":
        # Windows: Yu Gothic is excellent for Japanese on Windows
        return QFont("Yu Gothic", size)
    else:
        # Linux: Use system sans-serif (usually good CJK support)
        return QFont("Noto Sans CJK JP", size)


# Preset font configurations for common use cases
FONT_LABEL = get_font(("default", 9))
FONT_EXPORT_BUTTON = get_font(("default", 12))
FONT_MONOSPACE_SMALL = get_font(("monospace", 9))


def get_system_name() -> str:
    """Return the current OS name."""
    return platform.system()
