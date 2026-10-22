import re
from datetime import UTC, datetime

HISTORY_PAGE_SIZE = 5


def parse_history_callback(value: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"history:(page|view|details|evidence|sources|result):(\d+)", value)
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def parse_details_callback(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"history:details:(\d+)(?::(\d+))?", value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def format_history_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")
