"""Filename and path validation logic."""

from backend.app.core.errors import AppError

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def validate_filename(name: str) -> str:
    """Validates filename against security and cross-platform naming rules.

    Rejects control characters, path separators, and Windows reserved names.
    """
    if not name or not name.strip():
        raise AppError(400, "INVALID_FILENAME", "Filename cannot be empty")

    trimmed = name.strip()

    # Reject path separators
    if "/" in trimmed or "\\" in trimmed:
        raise AppError(
            400, "INVALID_FILENAME", "Filename cannot contain path separators ('/' or '\\')"
        )

    # Reject control characters (0-31 and 127)
    if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
        raise AppError(400, "INVALID_FILENAME", "Filename cannot contain control characters")

    # Check Windows reserved names
    base_name = trimmed.split(".")[0].upper()
    if base_name in WINDOWS_RESERVED_NAMES:
        raise AppError(
            400,
            "INVALID_FILENAME",
            f"Filename '{trimmed}' uses a reserved system name ({base_name})",
        )

    # Reject suspicious trailing dots or spaces
    if trimmed.endswith(".") or trimmed.endswith(" "):
        raise AppError(400, "INVALID_FILENAME", "Filename cannot end with a period or space")

    return trimmed
