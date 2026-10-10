import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from mcp.server.mcpserver.exceptions import ToolError

KOLKATA = ZoneInfo("Asia/Kolkata")
STATUSES = frozenset(
    {"pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"}
)


def positive_id(value: int) -> int:
    if value < 1:
        raise ToolError("order_id must be a positive integer")
    return value


def pagination(page: int, per_page: int) -> dict[str, str]:
    if not 1 <= page <= 1000 or not 1 <= per_page <= 50:
        raise ToolError("page must be 1..1000 and per_page must be 1..50")
    return {"page": str(page), "per_page": str(per_page)}


def product_input(name: str, price: str) -> dict[str, str]:
    name = name.strip()
    if not name or len(name) > 200:
        raise ToolError("name must contain 1..200 characters")
    if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?", price):
        raise ToolError("price must be a non-negative decimal string with at most two places")
    amount = Decimal(price)
    return {
        "name": name,
        "regular_price": format(amount, "f"),
        "type": "simple",
        "status": "publish",
    }


def order_status(value: str) -> str:
    if value not in STATUSES:
        raise ToolError("status must be one of: " + ", ".join(sorted(STATUSES)))
    return value


def order_dates(
    today: bool, after: str | None, before: str | None, now: datetime | None = None
) -> dict[str, str]:
    if today and (after or before):
        raise ToolError("today cannot be combined with after or before")
    if today:
        day = (now or datetime.now(KOLKATA)).astimezone(KOLKATA).date()
        start = datetime.combine(day, time.min, KOLKATA) - timedelta(seconds=1)
        end = datetime.combine(day + timedelta(days=1), time.min, KOLKATA)
        return {
            "after": start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S"),
            "before": end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S"),
            "dates_are_gmt": "true",
        }
    result: dict[str, str] = {}
    for key, value in (("after", after), ("before", before)):
        if value:
            try:
                boundary = date.fromisoformat(value)
            except ValueError as exc:
                raise ToolError(f"{key} must be an ISO date (YYYY-MM-DD)") from exc
            if key == "after":
                start = datetime.combine(boundary, time.min) - timedelta(seconds=1)
                result[key] = start.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                result[key] = datetime.combine(boundary + timedelta(days=1), time.min).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
    if after and before and after > before:
        raise ToolError("after must not be later than before")
    return result
