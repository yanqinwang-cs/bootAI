from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_bytes(size_bytes: int | None) -> str:
    if size_bytes is None or isinstance(size_bytes, bool) or size_bytes < 0:
        return "Not available"
    if size_bytes < 1024:
        return f"{size_bytes} B"

    value = float(size_bytes)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            rounded = f"{value:.1f}"
            if rounded.endswith(".0"):
                rounded = rounded[:-2]
            return f"{rounded} {unit}"
    return "Not available"


def format_local_time(
    value: datetime | None,
    *,
    now: datetime | None = None,
) -> str:
    if not isinstance(value, datetime):
        return "Not available"
    try:
        local_value = value.astimezone()
        local_now = (now or datetime.now().astimezone()).astimezone(
            local_value.tzinfo
        )
    except (OSError, OverflowError, ValueError):
        return "Not available"

    clock = _clock_text(local_value)
    if local_value.date() == local_now.date():
        return f"Today, {clock}"
    if local_value.date() == (local_now - timedelta(days=1)).date():
        return f"Yesterday, {clock}"
    month = _MONTHS[local_value.month - 1]
    return f"{local_value.day} {month} {local_value.year}, {clock}"


def format_local_timestamp(value: float | None) -> str:
    if value is None or isinstance(value, bool):
        return "Not available"
    try:
        timestamp = datetime.fromtimestamp(value).astimezone()
    except (OSError, OverflowError, TypeError, ValueError):
        return "Not available"
    return format_local_time(timestamp)


def folder_name(root: Path) -> str:
    return root.name or root.as_posix()


def readable_folder(path: Path, root: Path, *, include_root: bool) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return "Not available"

    parts = list(relative.parts)
    if include_root:
        parts.insert(0, folder_name(root))
    if not parts:
        return folder_name(root)
    return " → ".join(parts)


def _clock_text(value: datetime) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"
