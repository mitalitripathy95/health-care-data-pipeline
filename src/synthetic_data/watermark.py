"""Composite watermark helpers used by source extractors.

The source systems use a timestamp plus a stable primary key.  Comparing both
values prevents records sharing the same timestamp from being skipped.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any


def parse_timestamp(value: str | datetime) -> datetime:
    """Parse an ISO-8601 timestamp and require timezone information."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("watermark timestamps must include a timezone")
    return parsed


def watermark_tuple(timestamp: str | datetime, primary_key: int) -> tuple[datetime, int]:
    """Return a comparable ``(timestamp, primary_key)`` watermark."""
    return parse_timestamp(timestamp), int(primary_key)


def is_after(
    timestamp: str | datetime,
    primary_key: int,
    low_timestamp: str | datetime,
    low_primary_key: int,
) -> bool:
    """Whether a source row is strictly after the committed low watermark."""
    return watermark_tuple(timestamp, primary_key) > watermark_tuple(low_timestamp, low_primary_key)


def max_watermark(
    rows: Iterable[dict[str, Any]], timestamp_column: str, primary_key_column: str
) -> tuple[datetime, int] | None:
    """Return the greatest composite watermark in *rows*, or ``None`` if empty."""
    values = (watermark_tuple(row[timestamp_column], row[primary_key_column]) for row in rows)
    return max(values, default=None)


def select_after(
    rows: Iterable[dict[str, Any]],
    timestamp_column: str,
    primary_key_column: str,
    low_watermark: tuple[str | datetime, int],
) -> list[dict[str, Any]]:
    """Return rows strictly after a committed composite watermark."""
    low_timestamp, low_key = low_watermark
    return [
        row
        for row in rows
        if is_after(
            row[timestamp_column],
            row[primary_key_column],
            low_timestamp,
            low_key,
        )
    ]


__all__ = [
    "is_after",
    "max_watermark",
    "parse_timestamp",
    "select_after",
    "watermark_tuple",
]
