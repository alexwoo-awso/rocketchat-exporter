from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_iso_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    candidate = value.strip()
    if not candidate:
        raise ValueError("empty datetime value")
    if "T" not in candidate and len(candidate) == 10:
        parsed_date = datetime.fromisoformat(candidate).date()
        dt = datetime.combine(
            parsed_date,
            time.max if end_of_day else time.min,
        )
        return dt.replace(tzinfo=UTC)
    dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_csv(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    result: set[str] = set()
    for value in values:
        parts = [item.strip() for item in value.split(",")]
        result.update(item for item in parts if item)
    return result


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
