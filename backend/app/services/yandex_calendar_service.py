from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING

import os
import logging
from dateutil.tz import gettz

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    import caldav  # type: ignore

def _require_caldav():
    """
    Lazy import to avoid crashing the whole backend if CalDAV deps are not installed.
    Only Yandex Calendar endpoints allow/need these.
    """
    try:
        import caldav  # type: ignore
        import vobject  # type: ignore
        return caldav, vobject
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "Missing dependency for Yandex Calendar CalDAV integration. "
            "Install backend deps: `pip install -r requirements.txt` "
            "(or at least `pip install caldav`)."
        ) from e


@dataclass
class YandexCalendarConfig:
    url: str
    username: str
    password: str

    calendar_name: Optional[str] = None
    calendar_url: Optional[str] = None


def get_config_from_env() -> YandexCalendarConfig:
    base_url = (os.getenv("YANDEX_CALDAV_URL", "https://caldav.yandex.ru") or "").strip()
    # normalize url a bit (avoid accidental trailing spaces)
    if base_url.endswith("/"):
        base_url = base_url[:-1]

    username = (os.getenv("YANDEX_CALDAV_USERNAME", "") or "").strip()
    password = (os.getenv("YANDEX_CALDAV_PASSWORD", "") or "").strip()
    calendar_name = os.getenv("YANDEX_CALDAV_CALENDAR_NAME")
    calendar_url = os.getenv("YANDEX_CALDAV_CALENDAR_URL")

    # For Yandex CalDAV, we might need a more specific URL
    # Try to construct a proper CalDAV URL if username is provided
    url = base_url
    if username and "@" in username:
        # Extract email part (before @) for potential path construction
        email_part = username.split("@")[0]
        # Some CalDAV servers require /caldav/ path
        if not base_url.endswith("/caldav"):
            # Try common Yandex CalDAV paths
            # Note: This might need adjustment based on actual Yandex CalDAV structure
            pass  # Keep base URL as is for now, let caldav library handle discovery

    # Log config (without password) for debugging
    logger.info(f"Yandex CalDAV config: URL={url}, username={username}, has_password={bool(password)}")

    if not username or not password:
        raise ValueError(
            "YANDEX_CALDAV_USERNAME / YANDEX_CALDAV_PASSWORD are not set. "
            "Use a Yandex app password (recommended) or CalDAV password."
        )

    return YandexCalendarConfig(
        url=url,
        username=username,
        password=password,
        calendar_name=(calendar_name.strip() if isinstance(calendar_name, str) else calendar_name),
        calendar_url=(calendar_url.strip() if isinstance(calendar_url, str) else calendar_url),
    )


def _client(cfg: YandexCalendarConfig) -> caldav.DAVClient:
    caldav, _ = _require_caldav()
    # Log connection attempt (without password)
    logger.info(f"Attempting CalDAV connection: URL={cfg.url}, username={cfg.username}, password_length={len(cfg.password) if cfg.password else 0}")
    
    # For Yandex, we might need to specify principal URL explicitly
    # Try different approaches if standard connection fails
    try:
        client = caldav.DAVClient(url=cfg.url, username=cfg.username, password=cfg.password)
        logger.info("CalDAV client created successfully")
        return client
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Standard CalDAV connection failed: {error_msg}")
        
        # If it's an auth error, don't try alternative URLs
        if "Unauthorized" in error_msg or "401" in error_msg or "AuthorizationError" in error_msg:
            raise
        
        # If standard connection fails, try with explicit principal URL
        # Yandex CalDAV might require: https://caldav.yandex.ru/caldav/{username}/
        # Try with /caldav/ suffix if not present
        alt_url = cfg.url
        if not alt_url.endswith("/caldav") and not alt_url.endswith("/caldav/"):
            alt_url = f"{cfg.url}/caldav"
        logger.info(f"Trying alternative URL: {alt_url}")
        try:
            client = caldav.DAVClient(url=alt_url, username=cfg.username, password=cfg.password)
            logger.info("Alternative CalDAV URL worked")
            return client
        except Exception as alt_e:
            logger.error(f"Alternative URL also failed: {alt_e}")
            # Re-raise original error
            raise e


def _pick_calendar(principal: caldav.Principal, cfg: YandexCalendarConfig) -> caldav.Calendar:
    caldav, _ = _require_caldav()
    if cfg.calendar_url:
        calendar = caldav.Calendar(client=principal.client, url=cfg.calendar_url)
        logger.info(f"Using calendar by URL: {cfg.calendar_url}")
        return calendar

    calendars = principal.calendars()
    if not calendars:
        raise ValueError("No calendars found for this account.")

    # Логируем все доступные календари
    logger.info(f"Found {len(calendars)} calendars:")
    for idx, c in enumerate(calendars):
        try:
            props = c.get_properties([caldav.dav.DisplayName()])
            name = props.get("DisplayName") or props.get("{DAV:}displayname")
            url = str(getattr(c, "url", "unknown"))
        except Exception:
            name = None
            url = str(getattr(c, "url", "unknown"))
        logger.info(f"  [{idx}] Name: {name}, URL: {url}")

    if cfg.calendar_name:
        for c in calendars:
            try:
                props = c.get_properties([caldav.dav.DisplayName()])
                name = props.get("DisplayName") or props.get("{DAV:}displayname")
            except Exception:
                name = None
            if name and str(name).strip() == cfg.calendar_name.strip():
                logger.info(f"Using calendar by name: {cfg.calendar_name}")
                return c
        logger.warning(f"Calendar '{cfg.calendar_name}' not found, using first calendar")

    # Используем первый календарь по умолчанию
    selected = calendars[0]
    try:
        props = selected.get_properties([caldav.dav.DisplayName()])
        name = props.get("DisplayName") or props.get("{DAV:}displayname")
        url = str(getattr(selected, "url", "unknown"))
    except Exception:
        name = None
        url = str(getattr(selected, "url", "unknown"))
    logger.info(f"Using first calendar (default): Name={name}, URL={url}")
    return selected


def list_calendars(cfg: Optional[YandexCalendarConfig] = None) -> List[Dict[str, Any]]:
    caldav, _ = _require_caldav()
    cfg = cfg or get_config_from_env()
    
    try:
        logger.info(f"Connecting to Yandex CalDAV at {cfg.url} with username {cfg.username}")
        client = _client(cfg)
        principal = client.principal()
        logger.info("Successfully connected to Yandex CalDAV")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to connect to Yandex CalDAV: {error_msg}")
        
        # Provide more helpful error messages
        if "Unauthorized" in error_msg or "401" in error_msg:
            raise ValueError(
                "Yandex CalDAV authorization failed. "
                "Please check:\n"
                "1. YANDEX_CALDAV_USERNAME is correct (usually your Yandex email)\n"
                "2. YANDEX_CALDAV_PASSWORD is a Yandex App Password (not your regular password if 2FA is enabled)\n"
                "   To create App Password: https://id.yandex.ru/security/app-passwords\n"
                "3. No extra spaces in .env file values\n"
                "4. Backend was restarted after changing .env"
            ) from e
        elif "405" in error_msg or "Method Not Allowed" in error_msg or "PropfindError" in error_msg:
            raise ValueError(
                "Yandex CalDAV endpoint returned 405 Method Not Allowed. "
                "This usually means:\n"
                "1. The CalDAV URL might be incorrect. Try: https://caldav.yandex.ru\n"
                "2. Yandex might require a different CalDAV endpoint path\n"
                "3. Your account might not have CalDAV access enabled\n"
                "4. Try using YANDEX_CALDAV_CALENDAR_URL directly if you know the calendar URL\n"
                "\n"
                "Alternative: Export calendar as .ics file and import manually, "
                "or check Yandex Calendar settings for CalDAV access."
            ) from e
        raise

    out: List[Dict[str, Any]] = []
    for c in principal.calendars():
        name = None
        try:
            props = c.get_properties([caldav.dav.DisplayName()])
            name = props.get("DisplayName") or props.get("{DAV:}displayname")
        except Exception:
            pass

        out.append(
            {
                "name": str(name) if name is not None else None,
                "url": str(getattr(c, "url", None)),
            }
        )
    return out


def _ensure_tz(dt: datetime) -> datetime:
    """
    Гарантирует, что datetime имеет корректный tzinfo, понятный vobject/caldav.

    Ранее мы использовали встроенный timezone.utc, что приводило к ошибке:
    'Unable to guess TZID for tzinfo UTC' при сериализации VEVENT.
    Теперь явно используем dateutil.gettz('UTC'), который мапится на валидный TZID.
    
    vobject требует tzinfo из dateutil или pytz, а не стандартный timezone.utc.
    """
    utc_tz = gettz("UTC")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=utc_tz)

    # Проверяем тип tzinfo - если это стандартный timezone.utc, конвертируем
    tz_type_name = type(dt.tzinfo).__name__
    
    # Если это стандартный timezone из datetime - конвертируем
    if tz_type_name == 'timezone':
        # Проверяем, что это UTC (offset = 0)
        try:
            offset = dt.tzinfo.utcoffset(dt)
            if offset == timedelta(0):
                # Это UTC, заменяем tzinfo на dateutil UTC
                # Используем replace, так как время не меняется (UTC = UTC)
                return dt.replace(tzinfo=utc_tz)
        except (AttributeError, TypeError):
            pass
    
    # Проверяем по offset (на случай других вариантов UTC)
    try:
        offset = dt.tzinfo.utcoffset(dt) if hasattr(dt.tzinfo, 'utcoffset') else None
        if offset is not None and offset == timedelta(0):
            # Это UTC, но не dateutil - заменяем tzinfo
            return dt.replace(tzinfo=utc_tz)
    except (AttributeError, TypeError):
        pass
    
    # Проверяем прямое сравнение с timezone.utc
    if dt.tzinfo == timezone.utc:
        return dt.replace(tzinfo=utc_tz)
    
    # Если это уже dateutil или pytz tz - оставляем как есть
    return dt


def _build_vevent(
    uid: str,
    dtstart: datetime,
    dtend: datetime,
    summary: str,
    description: str,
) -> str:
    _, vobject = _require_caldav()
    
    # Убеждаемся, что все datetime имеют правильный tzinfo перед созданием vevent
    dtstamp = _ensure_tz(datetime.now(tz=timezone.utc))
    dtstart_clean = _ensure_tz(dtstart)
    dtend_clean = _ensure_tz(dtend)
    
    cal = vobject.iCalendar()
    ev = cal.add("vevent")
    ev.add("uid").value = uid
    ev.add("dtstamp").value = dtstamp
    ev.add("dtstart").value = dtstart_clean
    ev.add("dtend").value = dtend_clean
    ev.add("summary").value = summary
    ev.add("description").value = description
    return cal.serialize()


def upsert_event_by_uid(
    cfg: Optional[YandexCalendarConfig],
    uid: str,
    dtstart: datetime,
    duration_minutes: int,
    summary: str,
    description: str,
) -> Dict[str, Any]:
    caldav, _ = _require_caldav()
    """
    Upsert event into Yandex Calendar via CalDAV.

    Idempotency:
    - tries to find event by UID and update it
    - otherwise creates a new event
    """
    cfg = cfg or get_config_from_env()
    client = _client(cfg)
    principal = client.principal()
    calendar = _pick_calendar(principal, cfg)

    dtstart = _ensure_tz(dtstart)
    dtend = _ensure_tz(dtstart + timedelta(minutes=duration_minutes))

    ics = _build_vevent(uid=uid, dtstart=dtstart, dtend=dtend, summary=summary, description=description)

    # Try update if exists
    try:
        event = calendar.event_by_uid(uid)
        event.data = ics
        event.save()
        return {"action": "updated", "uid": uid, "href": str(getattr(event, "url", None))}
    except Exception:
        # Create new
        event = calendar.add_event(ics)
        return {"action": "created", "uid": uid, "href": str(getattr(event, "url", None))}

