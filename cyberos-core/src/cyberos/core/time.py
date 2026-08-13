from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC timestamp for internal event times."""

    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive timestamps and normalize aware values to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Naive datetime values are not allowed; provide timezone-aware UTC time")
    return value.astimezone(UTC)
