from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


MSK_TZ = ZoneInfo("Europe/Moscow")
LIVE_STYLIST_OPEN_HOUR = 10
LIVE_STYLIST_CLOSE_HOUR = 20
LIVE_STYLIST_WORKING_HOURS_TEXT = "10:00-20:00 по МСК"


def get_live_stylist_status(now: datetime | None = None) -> dict[str, object]:
    current_msk = now.astimezone(MSK_TZ) if now else datetime.now(MSK_TZ)
    is_open = LIVE_STYLIST_OPEN_HOUR <= current_msk.hour < LIVE_STYLIST_CLOSE_HOUR

    return {
        "timezone": "Europe/Moscow",
        "timezone_label": "по МСК",
        "working_hours": LIVE_STYLIST_WORKING_HOURS_TEXT,
        "status": "open" if is_open else "closed",
        "is_open": is_open,
        "status_text": (
            "На связи сейчас · до 20:00 по МСК"
            if is_open
            else "Сейчас не на связи · с 10:00 по МСК"
        ),
        "opens_at": "10:00",
        "closes_at": "20:00",
        "current_time": current_msk.isoformat(),
    }
