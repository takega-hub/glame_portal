import base64
import hashlib
import io
import json
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, update
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.marketing_campaign import MarketingCampaign
from app.models.advertising_connection import AdvertisingConnection
from app.models.advertising_daily_metric import AdvertisingDailyMetric
from app.models.app_setting import AppSetting
from app.services.yandex_metrika_service import YandexMetrikaService
from app.models.agent_interaction import InteractionStatus, AgentInteractionLog, AgentInteractionTask
from app.services.campaign_service import CampaignService
from app.agents.marketing_agent import MarketingAgent

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    type: str
    start_date: str  # ISO datetime
    end_date: Optional[str] = None  # ISO datetime
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None
    content_plan_id: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None


class CampaignAnalyticsStoreInput(BaseModel):
    metrika_counter_id: Optional[str] = None


class CampaignPlatformLinkInput(BaseModel):
    """Link an imported provider campaign to one GLAME campaign/project."""
    glame_campaign_id: Optional[UUID] = None
    traffic_project_task_id: Optional[UUID] = None


class CampaignResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    start_date: str
    end_date: Optional[str] = None
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None
    content_plan_id: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    external_source: Optional[str] = None
    external_id: Optional[str] = None
    advertising_connection_id: Optional[str] = None

    class Config:
        from_attributes = True


class AdvertisingConnectionInput(BaseModel):
    platform: str
    name: str
    account_login: Optional[str] = None
    client_login: Optional[str] = None
    organization_name: Optional[str] = None
    metrika_counter_id: Optional[str] = None
    permissions: Dict[str, Any] = {}
    is_active: bool = True


class AdvertisingConnectionSyncRequest(BaseModel):
    """Explicit manual sync request. OAuth secrets are never accepted here."""
    force: bool = False


class DirectTestCampaignInput(BaseModel):
    """A deliberately incomplete campaign used to verify Direct write access."""
    name: Optional[str] = None


class DirectProductionDraftInput(BaseModel):
    """A confirmed request to create a non-serving Direct campaign draft."""
    confirmation: str


class DirectProductionGroupInput(BaseModel):
    """A confirmed request to add one empty Unified ad group to a draft."""
    confirmation: str


class DirectProductionAdsInput(BaseModel):
    """A confirmed request to add a draft combinatorial ad to a Unified group."""
    confirmation: str
    titles: List[str]
    texts: List[str]


class DirectProductionKeywordsInput(BaseModel):
    """A confirmed request to add draft keyword targeting to a Unified group."""
    confirmation: str
    keywords: List[str]


class DirectProductionMediaAssetInput(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="GLAME media", min_length=1, max_length=255)


class DirectProductionImagesInput(BaseModel):
    """A confirmed request to upload selected GLAME-hosted images to Direct."""
    confirmation: str
    assets: List[DirectProductionMediaAssetInput] = Field(min_length=1, max_length=3)


class DirectProductionAttachImagesInput(BaseModel):
    """A confirmed request to attach previously uploaded image hashes to a draft ad."""
    confirmation: str


class DirectProductionModerationInput(BaseModel):
    """The irreversible final request to send one prepared Direct ad to moderation."""
    confirmation: str
    spending_acknowledged: bool = False


class YandexBusinessMapsDailyMetricsInput(BaseModel):
    """Facts entered from the Yandex Business/Maps cabinet until its API adapter is enabled."""
    connection_id: UUID
    metric_date: date
    card_opens: int = 0
    routes: int = 0
    calls: int = 0
    messages: int = 0
    website_clicks: int = 0


def _business_maps_raw_metrics(row: AdvertisingDailyMetric) -> Dict[str, int]:
    raw = row.raw_metrics or {}
    return {
        name: int(raw.get(name) or 0)
        for name in ("card_opens", "routes", "calls", "messages", "website_clicks")
    }


def _business_metrics_column(columns: List[Any], aliases: List[str]) -> Optional[str]:
    normalized = {str(column).strip().lower().replace("ё", "е"): column for column in columns}
    for alias in aliases:
        alias = alias.lower().replace("ё", "е")
        for name, original in normalized.items():
            if alias in name:
                return original
    return None


def _business_metrics_number(value: Any) -> int:
    try:
        return max(0, int(round(float(str(value or 0).replace("\u00a0", "").replace(" ", "").replace(",", ".")))))
    except (TypeError, ValueError):
        return 0


def _parse_yandex_business_html_export(content: bytes) -> pd.DataFrame:
    """Convert Yandex Business' HTML table served as ``.xls`` into daily rows.

    The export has metrics in rows and dates in columns, unlike a real Excel
    report.  Converting it here lets a marketer upload it without resaving it.
    """
    tables = pd.read_html(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    if not tables:
        raise ValueError("Yandex Business export has no table")
    table = tables[0]
    if table.empty or len(table.columns) < 2:
        raise ValueError("Yandex Business export has no daily columns")
    report_name = str(table.columns[0]).strip().lower().replace("ё", "е").replace("\u00a0", " ")
    is_profile_sources = "источник" in report_name and "профил" in report_name
    present_metrics: set[str] = set()
    if is_profile_sources:
        present_metrics.add("card_opens")
    else:
        for label_value in table.iloc[:, 0]:
            label = str(label_value).lower().replace("ё", "е").replace("\u00a0", " ")
            if "маршрут" in label:
                present_metrics.add("routes")
            elif "позвон" in label or "звонок" in label:
                present_metrics.add("calls")
            elif "сайт" in label:
                present_metrics.add("website_clicks")
            elif "сообщен" in label:
                present_metrics.add("messages")
            elif "профил" in label or "карточк" in label:
                present_metrics.add("card_opens")
    if not present_metrics:
        raise ValueError("Yandex Business export has no recognized metrics")
    daily_rows: List[Dict[str, Any]] = []
    for column in list(table.columns)[1:]:
        metric_date = pd.to_datetime(str(column), format="%d/%m/%Y", errors="coerce")
        if pd.isna(metric_date):
            continue  # the last column is the period total
        metrics = {"card_opens": 0, "routes": 0, "calls": 0, "messages": 0, "website_clicks": 0}
        for _, row in table.iterrows():
            label = str(row.iloc[0]).lower().replace("ё", "е").replace("\u00a0", " ")
            value = _business_metrics_number(row.get(column))
            if is_profile_sources:
                # Maps, Search and Navigator are all openings of this profile.
                metrics["card_opens"] += value
            elif "маршрут" in label:
                metrics["routes"] += value
            elif "позвон" in label or "звонок" in label:
                metrics["calls"] += value
            elif "сайт" in label:
                metrics["website_clicks"] += value
            elif "сообщен" in label:
                metrics["messages"] += value
            elif "профил" in label or "карточк" in label:
                metrics["card_opens"] += value
        # Do not emit artificial zero columns. A second report (for example,
        # calls and routes) must supplement profile openings from the first one.
        daily_rows.append({"Дата": metric_date.date(), **{name: metrics[name] for name in present_metrics}})
    if not daily_rows:
        raise ValueError("Yandex Business export has no daily dates")
    return pd.DataFrame(daily_rows)


class YandexOAuthSettingsInput(BaseModel):
    client_id: str
    client_secret: Optional[str] = None


class YandexMetrikaSettingsInput(BaseModel):
    name: str = "Сайт GLAME"
    counter_id: str
    oauth_token: Optional[str] = None


def _connection_payload(item: AdvertisingConnection, oauth_configured: Optional[bool] = None) -> Dict[str, Any]:
    return {
        "id": str(item.id), "platform": item.platform, "name": item.name,
        "account_login": item.account_login, "client_login": item.client_login,
        "organization_name": item.organization_name, "status": item.status,
        "auth_mode": item.auth_mode, "permissions": item.permissions or {},
        "metrika_counter_id": (item.permissions or {}).get("metrika_counter_id"),
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "last_sync_status": item.last_sync_status, "last_sync_summary": item.last_sync_summary,
        "is_active": item.is_active,
        "oauth_configured": bool(os.getenv("YANDEX_OAUTH_CLIENT_ID")) if oauth_configured is None else oauth_configured,
    }


def _require_ad_admin(user: Optional[User]) -> User:
    if not user or str(getattr(user, "role", "") or "") not in {"admin", "ai_marketer", "content_manager"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав для управления рекламными кабинетами")
    return user


async def _get_app_setting(db: AsyncSession, key: str) -> Optional[str]:
    item = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return item.value.strip() if item and item.value else None


async def _set_app_setting(db: AsyncSession, key: str, value: str) -> None:
    item = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if item:
        item.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _yandex_secret_cipher() -> Fernet:
    """Derive a server-only encryption key; encrypted values never leave the API."""
    material = (os.getenv("YANDEX_OAUTH_ENCRYPTION_KEY") or os.getenv("JWT_SECRET_KEY") or "").encode("utf-8")
    if not material:
        raise RuntimeError("JWT_SECRET_KEY or YANDEX_OAUTH_ENCRYPTION_KEY must be configured")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material + b":yandex-oauth").digest()))


def _encrypt_yandex_secret(value: str) -> str:
    return _yandex_secret_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_yandex_secret(value: str) -> str:
    try:
        return _yandex_secret_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


async def _yandex_oauth_settings(db: AsyncSession) -> tuple[str, str]:
    """Platform-managed values take priority; environment remains a deployment fallback."""
    client_id = await _get_app_setting(db, "yandex_oauth_client_id") or os.getenv("YANDEX_OAUTH_CLIENT_ID", "").strip()
    encrypted_secret = await _get_app_setting(db, "yandex_oauth_client_secret_encrypted")
    client_secret = _decrypt_yandex_secret(encrypted_secret) if encrypted_secret else os.getenv("YANDEX_OAUTH_CLIENT_SECRET", "").strip()
    return client_id, client_secret


async def _yandex_metrika_counters(db: AsyncSession) -> List[Dict[str, str]]:
    """Return every configured Metrika counter, including the legacy site counter."""
    serialized = await _get_app_setting(db, "yandex_metrika_counters")
    try:
        stored = json.loads(serialized) if serialized else []
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = []
    counters: List[Dict[str, str]] = []
    for item in stored if isinstance(stored, list) else []:
        if not isinstance(item, dict):
            continue
        counter_id = str(item.get("counter_id") or "").strip()
        token = _decrypt_yandex_secret(str(item.get("oauth_token_encrypted") or ""))
        if counter_id and token:
            counters.append({"id": str(item.get("id") or uuid.uuid4()), "name": str(item.get("name") or f"Счётчик {counter_id}").strip(), "counter_id": counter_id, "oauth_token": token})
    legacy_counter_id = await _get_app_setting(db, "yandex_metrika_counter_id") or os.getenv("YANDEX_METRIKA_COUNTER_ID", "").strip()
    legacy_encrypted = await _get_app_setting(db, "yandex_metrika_oauth_token_encrypted")
    legacy_token = _decrypt_yandex_secret(legacy_encrypted) if legacy_encrypted else os.getenv("YANDEX_METRIKA_OAUTH_TOKEN", "").strip()
    if legacy_counter_id and legacy_token and not any(item["counter_id"] == legacy_counter_id for item in counters):
        counters.insert(0, {"id": "legacy-site", "name": "Сайт GLAME", "counter_id": legacy_counter_id, "oauth_token": legacy_token})
    return counters


def _metrika_counter_payload(item: Dict[str, str]) -> Dict[str, str]:
    return {"id": item["id"], "name": item["name"], "counter_id": item["counter_id"]}


def _callback_url(request: Request, connection_id: UUID) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.url.scheme
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    if not host or any(char.isspace() for char in host):
        raise HTTPException(status_code=400, detail="Не удалось определить публичный адрес платформы для OAuth callback.")
    return f"{scheme}://{host}/api/marketing/advertising-connections/{connection_id}/oauth/callback"


def _authorization_complete_page(title: str, text: str, success: bool) -> HTMLResponse:
    color = "#16794a" if success else "#b42318"
    return HTMLResponse(
        f"<!doctype html><html lang='ru'><meta charset='utf-8'><title>{title}</title>"
        f"<body style='font-family:Arial,sans-serif;max-width:640px;margin:72px auto;padding:0 24px'>"
        f"<h1 style='color:{color}'>{title}</h1><p>{text}</p><p>Это окно можно закрыть и вернуться в GLAME.</p></body></html>"
    )


def _direct_campaign_status(campaign: Dict[str, Any]) -> str:
    state = str(campaign.get("State") or "").upper()
    if state == "ON":
        return "active"
    if state in {"OFF", "SUSPENDED"}:
        return "paused"
    if state == "ARCHIVED":
        return "archived"
    if state in {"ENDED", "CONVERTED"}:
        return "completed"
    return "draft"


def _direct_start_date(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(f"{str(value)}T00:00:00+03:00")
    except ValueError:
        return datetime.now(timezone.utc)


async def _sync_yandex_direct_campaigns(
    db: AsyncSession,
    connection: AdvertisingConnection,
    token: str,
    imported_by: Optional[User],
) -> Dict[str, int]:
    """Import campaign metadata through the read-only Campaigns.get method only."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    request_body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "Type", "State", "Status", "StatusPayment", "StartDate", "EndDate", "DailyBudget"],
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.direct.yandex.com/json/v501/campaigns", headers=headers, json=request_body)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or payload.get("error"):
        error = payload.get("error") or {}
        code = error.get("error_code") or response.status_code
        message = error.get("error_string") or "Яндекс Директ вернул ошибку при чтении кампаний"
        raise HTTPException(status_code=502, detail={"message": message, "provider_code": code})
    rows = ((payload.get("result") or {}).get("Campaigns") or [])
    created = 0
    updated = 0
    for remote in rows:
        external_id = str(remote.get("Id") or "")
        if not external_id:
            continue
        existing = (
            await db.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.advertising_connection_id == connection.id,
                    MarketingCampaign.external_id == external_id,
                )
            )
        ).scalar_one_or_none()
        daily_budget = (remote.get("DailyBudget") or {}).get("Amount")
        budget = float(daily_budget) / 1_000_000 if daily_budget is not None else None
        fields = {
            "name": str(remote.get("Name") or f"Яндекс Директ #{external_id}"),
            "type": "paid",
            "status": _direct_campaign_status(remote),
            "start_date": _direct_start_date(remote.get("StartDate")),
            "end_date": _direct_start_date(remote["EndDate"]) if remote.get("EndDate") else None,
            "budget": budget,
            "channels": ["yandex_direct"],
            "target_audience": {"source": "yandex_direct", "connection_id": str(connection.id)},
            "metrics": {
                **((existing.metrics or {}) if existing else {}),
                "yandex_campaign_id": external_id,
                "yandex_type": remote.get("Type"),
                "yandex_state": remote.get("State"),
                "yandex_status": remote.get("Status"),
                "yandex_status_payment": remote.get("StatusPayment"),
                "import_mode": "read_only",
            },
            "external_source": "yandex_direct",
            "external_id": external_id,
            "advertising_connection_id": connection.id,
        }
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(MarketingCampaign(**fields, user_id=imported_by.id if imported_by else None))
            created += 1
    return {"received": len(rows), "created": created, "updated": updated}


@router.patch("/campaigns/{campaign_id}/analytics-store")
async def assign_campaign_analytics_store(
    campaign_id: UUID,
    body: CampaignAnalyticsStoreInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Bind one Direct/GLAME campaign to one store counter for scoped analytics."""
    _require_ad_admin(current_user)
    campaign = await db.get(MarketingCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена.")
    counter_id = (body.metrika_counter_id or "").strip()
    if counter_id:
        available = await _yandex_metrika_counters(db)
        if not any(item["id"] == counter_id for item in available):
            raise HTTPException(status_code=400, detail="Выберите существующий счётчик Метрики.")
    metrics = dict(campaign.metrics or {})
    if counter_id:
        metrics["metrika_counter_id"] = counter_id
    else:
        metrics.pop("metrika_counter_id", None)
    campaign.metrics = metrics
    await db.commit()
    return {"id": str(campaign.id), "metrika_counter_id": counter_id}


@router.patch("/campaigns/{campaign_id}/platform-link")
async def link_imported_campaign_to_glame_campaign(
    campaign_id: UUID,
    body: CampaignPlatformLinkInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Store a deliberate one-to-one relationship between Direct and a GLAME campaign."""
    _require_ad_admin(current_user)
    imported = await db.get(MarketingCampaign, campaign_id)
    if not imported:
        raise HTTPException(status_code=404, detail="Импортированная кампания не найдена.")
    if imported.external_source != "yandex_direct":
        raise HTTPException(status_code=409, detail="Связать с проектом GLAME можно только кампанию, импортированную из Яндекс Директа.")

    linked_id = body.glame_campaign_id
    if linked_id:
        linked = await db.get(MarketingCampaign, linked_id)
        if not linked:
            raise HTTPException(status_code=404, detail="Кампания GLAME для связи не найдена.")
        if linked.id == imported.id or linked.external_source == "yandex_direct":
            raise HTTPException(status_code=400, detail="Выберите внутреннюю кампанию GLAME, а не другую кампанию Директа.")

    metrics = dict(imported.metrics or {})
    if linked_id:
        metrics["linked_glame_campaign_id"] = str(linked_id)
    else:
        metrics.pop("linked_glame_campaign_id", None)
    if body.traffic_project_task_id:
        metrics["linked_traffic_project_task_id"] = str(body.traffic_project_task_id)
    else:
        metrics.pop("linked_traffic_project_task_id", None)
    imported.metrics = metrics
    await db.commit()
    return {
        "id": str(imported.id),
        "glame_campaign_id": str(linked_id) if linked_id else None,
        "traffic_project_task_id": str(body.traffic_project_task_id) if body.traffic_project_task_id else None,
    }


def _report_number(value: Any) -> float:
    """Yandex reports are TSV and may use either decimal separator."""
    try:
        return float(str(value or "0").replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


async def _sync_yandex_direct_daily_metrics(
    db: AsyncSession,
    connection: AdvertisingConnection,
    token: str,
    days: int = 14,
) -> Dict[str, Any]:
    """Import campaign daily facts through the Direct Reports endpoint only."""
    today = datetime.now(timezone.utc).date()
    date_from = today - timedelta(days=max(1, min(days, 90)) - 1)
    payload = {
        "params": {
            "SelectionCriteria": {"DateFrom": date_from.isoformat(), "DateTo": (today - timedelta(days=1)).isoformat()},
            "FieldNames": ["Date", "CampaignId", "Impressions", "Clicks", "Cost", "Conversions"],
            "ReportName": f"glame_daily_campaigns_{connection.id}_{today.isoformat()}",
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "NO",
            "IncludeDiscount": "NO",
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipReportSummary": "true",
    }
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://api.direct.yandex.com/json/v5/reports", headers=headers, json=payload)
    if response.status_code in {201, 202}:
        return {"received": 0, "upserted": 0, "pending": True}
    if response.status_code >= 400:
        try:
            error_payload = response.json().get("error") or {}
        except ValueError:
            error_payload = {}
        raise HTTPException(
            status_code=502,
            detail={"message": error_payload.get("error_string") or "Яндекс Директ вернул ошибку при чтении статистики", "provider_code": error_payload.get("error_code") or response.status_code},
        )
    lines = [line for line in response.text.splitlines() if line.strip()]
    if not lines:
        return {"received": 0, "upserted": 0, "pending": False}
    header = [cell.strip() for cell in lines[0].split("\t")]
    rows = [dict(zip(header, line.split("\t"))) for line in lines[1:]]
    campaigns = {
        str(item.external_id): item
        for item in (await db.execute(select(MarketingCampaign).where(MarketingCampaign.advertising_connection_id == connection.id))).scalars().all()
    }
    upserted = 0
    for raw in rows:
        external_id = str(raw.get("CampaignId") or "").strip()
        date_raw = str(raw.get("Date") or "").strip()
        if not external_id or not date_raw:
            continue
        try:
            metric_date = date.fromisoformat(date_raw)
        except ValueError:
            continue
        item = (
            await db.execute(
                select(AdvertisingDailyMetric).where(
                    AdvertisingDailyMetric.advertising_connection_id == connection.id,
                    AdvertisingDailyMetric.external_campaign_id == external_id,
                    AdvertisingDailyMetric.metric_date == metric_date,
                )
            )
        ).scalar_one_or_none()
        values = {
            "marketing_campaign_id": campaigns.get(external_id).id if campaigns.get(external_id) else None,
            "impressions": int(_report_number(raw.get("Impressions"))),
            "clicks": int(_report_number(raw.get("Clicks"))),
            "cost": _report_number(raw.get("Cost")),
            "conversions": _report_number(raw.get("Conversions")),
            "raw_metrics": raw,
        }
        if item:
            for key, value in values.items():
                setattr(item, key, value)
        else:
            db.add(AdvertisingDailyMetric(
                advertising_connection_id=connection.id,
                external_campaign_id=external_id,
                metric_date=metric_date,
                **values,
            ))
        upserted += 1
    return {"received": len(rows), "upserted": upserted, "pending": False}


@router.get("/advertising-connections")
async def list_advertising_connections(db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    _require_ad_admin(current_user)
    result = await db.execute(select(AdvertisingConnection).order_by(desc(AdvertisingConnection.created_at)))
    client_id, client_secret = await _yandex_oauth_settings(db)
    return [_connection_payload(item, bool(client_id and client_secret)) for item in result.scalars().all()]


@router.get("/advertising-connections/oauth-readiness")
async def advertising_oauth_readiness(db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    """Public configuration state only: no client secret or access token."""
    _require_ad_admin(current_user)
    client_id, client_secret = await _yandex_oauth_settings(db)
    return {
        "configured": bool(client_id and client_secret),
        "client_id_configured": bool(client_id),
        "client_secret_configured": bool(client_secret),
        "redirect_uri_configured": True,
        "client_id": client_id or None,
        "redirect_uri": "https://oauth.yandex.ru/verification_code",
        "message": (
            "OAuth-приложение Яндекса готово к подключению через безопасный веб-callback."
            if client_id and client_secret
            else "Введите Client ID и Client secret созданного OAuth-приложения Яндекса."
        ),
    }


@router.put("/advertising-connections/oauth-settings")
async def save_advertising_oauth_settings(
    body: YandexOAuthSettingsInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Save OAuth credentials with encrypted client secret from the platform interface."""
    _require_ad_admin(current_user)
    client_id = body.client_id.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="Укажите Client ID из OAuth-приложения Яндекса.")
    _, existing_secret = await _yandex_oauth_settings(db)
    if not (body.client_secret and body.client_secret.strip()) and not existing_secret:
        raise HTTPException(status_code=400, detail="Укажите Client secret. Он будет зашифрован перед сохранением.")
    await _set_app_setting(db, "yandex_oauth_client_id", client_id)
    if body.client_secret and body.client_secret.strip():
        await _set_app_setting(db, "yandex_oauth_client_secret_encrypted", _encrypt_yandex_secret(body.client_secret.strip()))
    await db.commit()
    _, client_secret = await _yandex_oauth_settings(db)
    return {
        "configured": bool(client_secret),
        "client_id_configured": True,
        "client_secret_configured": bool(client_secret),
        "redirect_uri_configured": True,
        "client_id": client_id,
        "redirect_uri": "https://oauth.yandex.ru/verification_code",
        "message": "Данные OAuth-приложения сохранены. Следующий шаг — авторизация владельца кабинета.",
    }


@router.get("/advertising-analytics/yandex-metrika-settings")
async def yandex_metrika_settings_readiness(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    _require_ad_admin(current_user)
    counters = await _yandex_metrika_counters(db)
    return {
        "configured": bool(counters),
        "counter_id": counters[0]["counter_id"] if counters else None,
        "oauth_token_configured": bool(counters),
        "counters": [_metrika_counter_payload(item) for item in counters],
    }


@router.put("/advertising-analytics/yandex-metrika-settings")
async def save_yandex_metrika_settings(
    body: YandexMetrikaSettingsInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    _require_ad_admin(current_user)
    counter_id = body.counter_id.strip()
    name = body.name.strip() or f"Счётчик {counter_id}"
    if not counter_id:
        raise HTTPException(status_code=400, detail="Укажите ID счётчика Яндекс Метрики.")
    existing_counters = await _yandex_metrika_counters(db)
    oauth_token = (body.oauth_token or "").strip()
    if not oauth_token and existing_counters:
        # The first secured token can be reused for another counter when the
        # same Yandex account has access to both counters. It is never sent to
        # the browser or returned by this endpoint.
        oauth_token = existing_counters[0]["oauth_token"]
    if not oauth_token:
        raise HTTPException(status_code=400, detail="Укажите OAuth-токен Метрики. Он будет зашифрован перед сохранением.")
    serialized = await _get_app_setting(db, "yandex_metrika_counters")
    try:
        stored = json.loads(serialized) if serialized else []
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = []
    stored = [item for item in stored if isinstance(item, dict) and str(item.get("counter_id") or "") != counter_id]
    stored.append({"id": str(uuid.uuid4()), "name": name, "counter_id": counter_id, "oauth_token_encrypted": _encrypt_yandex_secret(oauth_token)})
    await _set_app_setting(db, "yandex_metrika_counters", json.dumps(stored, ensure_ascii=False, separators=(",", ":")))
    await db.commit()
    counters = await _yandex_metrika_counters(db)
    return {"configured": bool(counters), "counter_id": counters[0]["counter_id"] if counters else None, "oauth_token_configured": bool(counters), "counters": [_metrika_counter_payload(item) for item in counters]}


@router.post("/advertising-connections/{connection_id}/authorization-link")
async def create_advertising_authorization_link(
    connection_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Create a short-lived, one-time OAuth state for an account owner."""
    _require_ad_admin(current_user)
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    client_id, client_secret = await _yandex_oauth_settings(db)
    if not client_id or not client_secret:
        raise HTTPException(status_code=409, detail="Сначала сохраните Client ID и Client secret OAuth-приложения Яндекса.")
    callback_url = _callback_url(request, connection_id)
    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    await _set_app_setting(
        db,
        f"yandex_oauth_state_{state}",
        _encrypt_yandex_secret(json.dumps({"connection_id": str(connection_id), "expires_at": expires_at.isoformat()})),
    )
    connection.status = "awaiting_account_authorization"
    connection.last_sync_status = "authorization_link_created"
    connection.last_sync_summary = {"message": "Ссылка авторизации создана; срок действия 15 минут."}
    await db.commit()
    authorization_url = "https://oauth.yandex.ru/authorize?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_url,
        "state": state,
    })
    return {
        "authorization_url": authorization_url,
        "callback_url": callback_url,
        "expires_at": expires_at.isoformat(),
        "instruction": "Добавьте этот Callback URL в настройках OAuth-приложения Яндекса как Web service, затем откройте ссылку и войдите под владельцем кабинета.",
    }


@router.get("/advertising-connections/{connection_id}/oauth/callback", response_class=HTMLResponse)
async def finish_advertising_authorization(
    connection_id: UUID,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Yandex authorization code server-side and save an encrypted account token."""
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection:
        return _authorization_complete_page("Кабинет не найден", "Запрос относится к удалённому или недоступному кабинету.", False)
    if error:
        connection.last_sync_status = "authorization_denied"
        connection.last_sync_summary = {"message": error_description or error}
        await db.commit()
        return _authorization_complete_page("Авторизация отменена", "Яндекс не выдал доступ к рекламному кабинету.", False)
    encrypted_state = await _get_app_setting(db, f"yandex_oauth_state_{state}") if state else None
    # Compatibility with links created before state was stored per request.
    if not encrypted_state:
        encrypted_state = await _get_app_setting(db, f"yandex_oauth_state_{connection_id}")
    try:
        state_data = json.loads(_decrypt_yandex_secret(encrypted_state or ""))
        stored_connection_id = str(state_data.get("connection_id") or connection_id)
        valid_state = bool(state) and secrets.compare_digest(stored_connection_id, str(connection_id))
        if state_data.get("state"):
            valid_state = valid_state and secrets.compare_digest(state, str(state_data.get("state")))
        valid_expiry = datetime.fromisoformat(state_data["expires_at"]) > datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError):
        valid_state = False
        valid_expiry = False
    if not code or not valid_state or not valid_expiry:
        return _authorization_complete_page("Недействительная авторизация", "Ссылка устарела или не прошла проверку безопасности. Вернитесь в GLAME и создайте новую.", False)
    client_id, client_secret = await _yandex_oauth_settings(db)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth.yandex.ru/token",
                data={"grant_type": "authorization_code", "code": code, "client_id": client_id, "client_secret": client_secret},
            )
        payload = response.json()
        access_token = str(payload.get("access_token") or "")
        if response.status_code >= 400 or not access_token:
            raise ValueError(str(payload.get("error_description") or payload.get("error") or "Yandex не выдал OAuth-токен"))
    except Exception:
        connection.last_sync_status = "token_exchange_failed"
        connection.last_sync_summary = {"message": "Не удалось получить OAuth-токен. Повторите авторизацию или проверьте Callback URL в Яндекс OAuth."}
        await db.commit()
        return _authorization_complete_page("Не удалось завершить авторизацию", "Проверьте Callback URL и попробуйте ещё раз из GLAME.", False)
    token_key = f"yandex_oauth_token_{connection_id}"
    await _set_app_setting(db, token_key, _encrypt_yandex_secret(access_token))
    if state:
        await _set_app_setting(db, f"yandex_oauth_state_{state}", "")
    connection.secret_ref = f"app_settings:{token_key}"
    connection.status = "connected"
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "authorized"
    connection.last_sync_summary = {"message": "Владелец кабинета авторизован. Можно запускать read-only синхронизацию кампаний."}
    await db.commit()
    return _authorization_complete_page("Кабинет подключён", "GLAME получил защищённый OAuth-доступ владельца. Вернитесь в Traffic & Growth и запустите синхронизацию.", True)


@router.post("/advertising-connections")
async def create_advertising_connection(body: AdvertisingConnectionInput, db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    user = _require_ad_admin(current_user)
    if body.platform not in {"yandex_direct", "yandex_business", "yandex_maps"}:
        raise HTTPException(status_code=400, detail="Неподдерживаемая рекламная площадка")
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    metrika_counter_id = (payload.pop("metrika_counter_id", None) or "").strip() if body.platform in {"yandex_business", "yandex_maps"} else ""
    permissions = dict(payload.get("permissions") or {})
    if metrika_counter_id:
        permissions["metrika_counter_id"] = metrika_counter_id
    else:
        permissions.pop("metrika_counter_id", None)
    payload["permissions"] = permissions
    is_direct = body.platform == "yandex_direct"
    item = AdvertisingConnection(
        **payload,
        created_by=user.id,
        status="awaiting_oauth" if is_direct else "connected",
        last_sync_status=None if is_direct else "manual_source_ready",
        last_sync_summary=None if is_direct else {"message": "Источник Яндекс Бизнес/Карт подключён. Дневные действия карточки вносятся в единой аналитике до подключения read-only API."},
    )
    db.add(item); await db.commit(); await db.refresh(item)
    client_id, client_secret = await _yandex_oauth_settings(db)
    return _connection_payload(item, bool(client_id and client_secret))


@router.patch("/advertising-connections/{connection_id}")
async def update_advertising_connection(connection_id: UUID, body: AdvertisingConnectionInput, db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_current_user)):
    _require_ad_admin(current_user)
    item = await db.get(AdvertisingConnection, connection_id)
    if not item: raise HTTPException(status_code=404, detail="Кабинет не найден")
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    metrika_counter_id = (payload.pop("metrika_counter_id", None) or "").strip() if body.platform in {"yandex_business", "yandex_maps"} else ""
    permissions = dict(payload.get("permissions") or item.permissions or {})
    if metrika_counter_id:
        permissions["metrika_counter_id"] = metrika_counter_id
    else:
        permissions.pop("metrika_counter_id", None)
    payload["permissions"] = permissions
    authorization_identity_changed = any(
        getattr(item, key) != payload.get(key)
        for key in ("platform", "account_login", "client_login")
    )
    for key, value in payload.items():
        setattr(item, key, value)
    if authorization_identity_changed:
        # A token is bound to an app + Yandex user + account context. Never
        # reuse it after changing the target platform or advertiser account.
        await _set_app_setting(db, f"yandex_oauth_token_{connection_id}", "")
        item.secret_ref = None
        item.status = "awaiting_account_authorization"
        item.last_sync_status = "reauthorization_required"
        item.last_sync_summary = {"message": "Площадка или рекламный аккаунт изменены. Нужна новая авторизация владельца."}
    await db.commit(); await db.refresh(item)
    client_id, client_secret = await _yandex_oauth_settings(db)
    return _connection_payload(item, bool(client_id and client_secret))


@router.delete("/advertising-connections/{connection_id}")
async def delete_advertising_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Remove an advertising connection and its protected credentials/facts only."""
    _require_ad_admin(current_user)
    item = await db.get(AdvertisingConnection, connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    metrics_result = await db.execute(delete(AdvertisingDailyMetric).where(AdvertisingDailyMetric.advertising_connection_id == connection_id))
    await db.execute(update(MarketingCampaign).where(MarketingCampaign.advertising_connection_id == connection_id).values(advertising_connection_id=None))
    await db.execute(delete(AppSetting).where(AppSetting.key == f"yandex_oauth_token_{connection_id}"))
    await db.delete(item)
    await db.commit()
    return {"status": "deleted", "connection_id": str(connection_id), "daily_metrics_deleted": metrics_result.rowcount or 0}


@router.post("/advertising-connections/{connection_id}/test-direct-campaign")
async def create_direct_test_campaign(
    connection_id: UUID,
    body: DirectTestCampaignInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Create a non-serving Unified Performance Campaign to verify Direct write access.

    The campaign is intentionally created without ad groups or ads. It therefore
    remains a draft and cannot spend money or be sent to moderation from GLAME.
    """
    user = _require_ad_admin(current_user)
    item = await db.get(AdvertisingConnection, connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    if item.platform != "yandex_direct":
        raise HTTPException(status_code=409, detail="Тестовая кампания через API доступна только для Яндекс Директа.")
    if not item.is_active:
        raise HTTPException(status_code=409, detail="Кабинет отключён. Сначала включите его в реестре.")

    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")

    name = (body.name or "").strip() or f"GLAME API TEST — ЕПК черновик {date.today().isoformat()} {secrets.token_hex(3)}"
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Название тестовой кампании не должно превышать 255 символов.")
    request_body = {
        "method": "add",
        "params": {
            "Campaigns": [{
                "Name": name,
                "StartDate": date.today().isoformat(),
                "UnifiedCampaign": {
                    "BiddingStrategy": {
                        "Search": {
                            "BiddingStrategyType": "AVERAGE_CPC",
                            "AverageCpc": {"AverageCpc": 1_000_000, "WeeklySpendLimit": 300_000_000},
                        },
                        "Network": {"BiddingStrategyType": "NETWORK_DEFAULT"},
                    },
                },
            }],
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    if item.client_login:
        headers["Client-Login"] = item.client_login
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/campaigns", headers=headers, json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    result = ((payload.get("result") or {}).get("AddResults") or [{}])[0]
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error or not result.get("Id"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не создал тестовую кампанию.",
                "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code,
            },
        )

    imported = await _sync_yandex_direct_campaigns(db, item, token, user)
    item.status = "connected"
    item.last_sync_at = datetime.now(timezone.utc)
    item.last_sync_status = "test_campaign_created"
    item.last_sync_summary = {
        "campaigns_imported": imported["received"],
        "created": imported["created"],
        "updated": imported["updated"],
        "test_campaign_id": str(result["Id"]),
        "test_campaign_name": name,
        "message": "Создан безопасный тестовый черновик ЕПК без групп и объявлений. Показы и списания невозможны.",
    }
    await db.commit()
    await db.refresh(item)
    return {**_connection_payload(item), "test_campaign_id": str(result["Id"]), "test_campaign_name": name}


@router.post("/traffic-projects/{task_id}/direct-production-draft")
async def create_direct_production_draft(
    task_id: UUID,
    body: DirectProductionDraftInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Create the explicitly confirmed, non-serving Direct campaign draft.

    This is deliberately the first and only write step of the production flow.
    It creates a Unified campaign with the selected Metrika counter, but no ad
    groups and no ads. Consequently it cannot be moderated, shown, or spend
    money. Adding groups, ads, and enabling the campaign remain separate,
    explicitly confirmed steps.
    """
    user = _require_ad_admin(current_user)
    if body.confirmation.strip() != "СОЗДАТЬ ЧЕРНОВИК":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «СОЗДАТЬ ЧЕРНОВИК».")

    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "armed":
        raise HTTPException(status_code=409, detail="Сначала подготовьте боевой запуск: выберите кабинет, счётчик и согласуйте креативы.")

    try:
        connection_id = UUID(str(release.get("direct_connection_id")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="В подготовке запуска не указан кабинет Яндекс Директа.")
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform != "yandex_direct" or not connection.is_active or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Выбранный кабинет Яндекс Директа больше не подключён. Подготовьте запуск заново.")

    counter_ref = str(release.get("metrika_counter_id") or "")
    counters = await _yandex_metrika_counters(db)
    counter = next((entry for entry in counters if entry["id"] == counter_ref), None)
    if not counter or not str(counter.get("counter_id") or "").isdigit():
        raise HTTPException(status_code=409, detail="Выбранный счётчик Метрики не найден. Подготовьте запуск заново.")

    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")

    brief = task_context.get("traffic_campaign_brief") or {}
    daily_budget = float(release.get("daily_budget_rub") or brief.get("daily_budget_rub") or 0)
    if daily_budget <= 0:
        raise HTTPException(status_code=409, detail="В паспорте запуска укажите дневной бюджет больше нуля.")
    task_input = task.input_data or {}
    campaign_code = str(brief.get("campaign_code") or task_input.get("campaign_code") or task_input.get("title") or "GLAME")
    name = f"GLAME — {campaign_code} — ЕПК черновик {date.today().isoformat()}"
    name = name[:255]
    weekly_spend_limit = max(int(round(daily_budget * 7 * 1_000_000)), 1_000_000)
    request_body = {
        "method": "add",
        "params": {
            "Campaigns": [{
                "Name": name,
                "StartDate": date.today().isoformat(),
                "UnifiedCampaign": {
                    "BiddingStrategy": {
                        "Search": {
                            "BiddingStrategyType": "AVERAGE_CPC",
                            "AverageCpc": {"AverageCpc": 1_000_000, "WeeklySpendLimit": weekly_spend_limit},
                        },
                        "Network": {"BiddingStrategyType": "NETWORK_DEFAULT"},
                    },
                    "CounterIds": [int(counter["counter_id"])],
                },
            }],
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/campaigns", headers=headers, json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    result = ((payload.get("result") or {}).get("AddResults") or [{}])[0]
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error or not result.get("Id"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не создал черновик кампании.",
                "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code,
            },
        )

    direct_campaign_id = str(result["Id"])
    await _sync_yandex_direct_campaigns(db, connection, token, user)
    await db.flush()
    imported_campaign = (
        await db.execute(
            select(MarketingCampaign).where(
                MarketingCampaign.advertising_connection_id == connection.id,
                MarketingCampaign.external_id == direct_campaign_id,
            )
        )
    ).scalar_one_or_none()
    if imported_campaign:
        imported_metrics = dict(imported_campaign.metrics or {})
        imported_metrics.update({
            "metrika_counter_id": counter_ref,
            "linked_traffic_project_task_id": str(task.id),
            "production_draft": True,
            "production_draft_safety": "no_ad_groups_or_ads",
        })
        imported_campaign.metrics = imported_metrics

    task_context["direct_production_release"] = {
        **release,
        "status": "direct_draft_created",
        "direct_campaign_id": direct_campaign_id,
        "direct_campaign_name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "external_action": "draft_created_no_ad_groups_or_ads",
    }
    task.task_context = task_context
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_draft_created"
    connection.last_sync_summary = {
        "campaigns_imported": 1,
        "production_draft_id": direct_campaign_id,
        "production_draft_name": name,
        "message": "Создан черновик ЕПК с выбранным счётчиком Метрики. Группы и объявления не созданы: показы и списания невозможны.",
    }
    await db.commit()
    return {
        "status": "direct_draft_created",
        "direct_campaign_id": direct_campaign_id,
        "direct_campaign_name": name,
        "metrika_counter_id": counter_ref,
        "daily_budget_rub": daily_budget,
        "weekly_spend_limit_rub": weekly_spend_limit / 1_000_000,
        "safety": "no_ad_groups_or_ads",
    }


@router.post("/traffic-projects/{task_id}/direct-production-group")
async def create_direct_production_group(
    task_id: UUID,
    body: DirectProductionGroupInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Add one empty Unified group to an approved Direct campaign draft.

    The group deliberately has no ads, keywords, audience conditions, or
    moderation request. Direct reports such a group as DRAFT; it cannot serve
    because it contains no ad. Ads are an independently approved next step.
    """
    _require_ad_admin(current_user)
    if body.confirmation.strip() != "СОЗДАТЬ ГРУППУ":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «СОЗДАТЬ ГРУППУ».")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_draft_created":
        raise HTTPException(status_code=409, detail="Сначала создайте черновик ЕПК и завершите подготовку проекта.")
    checklist = release.get("publication_checklist") or {}
    if not all(checklist.get(key) is True for key in ("media_rights_confirmed", "promo_code_confirmed", "landing_confirmed")):
        raise HTTPException(status_code=409, detail="Перед созданием группы завершите контрольный лист публикации.")
    package = release.get("direct_publication_package") or {}
    group_name = str(package.get("ad_group_name") or "").strip()
    landing_url = str(package.get("landing_url") or "").strip()
    try:
        region_id = int(str(package.get("region_id") or ""))
        campaign_id = int(str(release.get("direct_campaign_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Сохраните корректный пакет группы и черновик кампании.")
    if not group_name or len(group_name) > 255 or not landing_url.startswith(("https://", "http://")) or region_id <= 0:
        raise HTTPException(status_code=409, detail="Для группы нужны название, локальный ID региона и корректная посадочная ссылка. Регион «0» для всей страны запрещён в GLAME.")
    if release.get("direct_group_id"):
        raise HTTPException(status_code=409, detail="Группа для этого черновика уже создана. Обновление группы будет отдельной операцией.")

    try:
        connection_id = UUID(str(release.get("direct_connection_id")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="В подготовке запуска не указан кабинет Яндекс Директа.")
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform != "yandex_direct" or not connection.is_active or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Выбранный кабинет Яндекс Директа больше не подключён.")
    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")

    headers = {"Authorization": f"Bearer {token}", "Accept-Language": "ru", "Content-Type": "application/json; charset=utf-8"}
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    request_body = {
        "method": "add",
        "params": {"AdGroups": [{
            "Name": group_name,
            "CampaignId": campaign_id,
            "RegionIds": [region_id],
            "UnifiedAdGroup": {"OfferRetargeting": "NO"},
        }]},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/adgroups", headers=headers, json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    result = ((payload.get("result") or {}).get("AddResults") or [{}])[0]
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error or not result.get("Id"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не создал группу.",
                "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code,
            },
        )
    group_id = str(result["Id"])
    task_context["direct_production_release"] = {
        **release,
        "status": "direct_group_created",
        "direct_group_id": group_id,
        "direct_group_name": group_name,
        "group_created_at": datetime.now(timezone.utc).isoformat(),
        "external_action": "empty_unified_ad_group_created_no_ads",
    }
    task.task_context = task_context
    direct_campaign = (
        await db.execute(select(MarketingCampaign).where(MarketingCampaign.advertising_connection_id == connection.id, MarketingCampaign.external_id == str(campaign_id)))
    ).scalar_one_or_none()
    if direct_campaign:
        metrics = dict(direct_campaign.metrics or {})
        metrics.update({"direct_ad_group_id": group_id, "direct_ad_group_name": group_name, "direct_ad_group_status": "DRAFT", "direct_publication_package": package})
        direct_campaign.metrics = metrics
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_group_created"
    connection.last_sync_summary = {"production_draft_id": str(campaign_id), "production_group_id": group_id, "message": "Создана пустая группа ЕПК без объявлений, ключевых фраз и условий показа. Показы и списания невозможны."}
    await db.commit()
    return {"status": "direct_group_created", "direct_campaign_id": str(campaign_id), "direct_group_id": group_id, "direct_group_name": group_name, "safety": "no_ads_keywords_or_targeting"}


def _validated_responsive_ad_copy(values: List[str], *, minimum: int, maximum: int, char_limit: int, word_limit: int, label: str) -> List[str]:
    cleaned = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not minimum <= len(cleaned) <= maximum:
        raise HTTPException(status_code=400, detail=f"{label}: укажите от {minimum} до {maximum} вариантов.")
    if len(set(item.casefold() for item in cleaned)) != len(cleaned):
        raise HTTPException(status_code=400, detail=f"{label}: удалите повторяющиеся варианты.")
    for item in cleaned:
        if len(item) > char_limit or any(len(word) > word_limit for word in item.split()):
            raise HTTPException(status_code=400, detail=f"{label}: «{item}» превышает ограничение Директа ({char_limit} символов, слово — до {word_limit}).")
    return cleaned


@router.post("/traffic-projects/{task_id}/direct-production-ads")
async def create_direct_production_ads(
    task_id: UUID,
    body: DirectProductionAdsInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Create one DRAFT combinatorial ad, without moderation or targeting.

    Direct now uses ResponsiveAd for new Unified campaign ads. The endpoint
    intentionally never calls Ads.moderate and the group still has no targeting
    criteria, so the created ad stays a non-serving DRAFT for review in GLAME.
    """
    _require_ad_admin(current_user)
    if body.confirmation.strip() != "СОЗДАТЬ ОБЪЯВЛЕНИЕ":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «СОЗДАТЬ ОБЪЯВЛЕНИЕ».")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_group_created":
        raise HTTPException(status_code=409, detail="Сначала создайте пустую Unified-группу.")
    if release.get("direct_ad_id"):
        raise HTTPException(status_code=409, detail="Черновик объявления для этой группы уже создан. Редактирование будет отдельной операцией.")
    package = release.get("direct_publication_package") or {}
    landing_url = str(package.get("landing_url") or "").strip()
    utm_template = str(package.get("utm_template") or "").strip().lstrip("?&")
    try:
        group_id = int(str(release.get("direct_group_id") or ""))
        connection_id = UUID(str(release.get("direct_connection_id")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Не найдена сохранённая группа или кабинет Директа.")
    if not landing_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=409, detail="В пакете группы укажите корректную посадочную ссылку.")
    titles = _validated_responsive_ad_copy(body.titles, minimum=1, maximum=7, char_limit=56, word_limit=22, label="Заголовки")
    texts = _validated_responsive_ad_copy(body.texts, minimum=1, maximum=3, char_limit=81, word_limit=23, label="Тексты")
    href = landing_url if not utm_template else f"{landing_url}{'&' if '?' in landing_url else '?'}{utm_template}"
    if len(href) > 1024:
        raise HTTPException(status_code=400, detail="Посадочная ссылка с UTM-шаблоном длиннее 1024 символов.")

    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform != "yandex_direct" or not connection.is_active or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Выбранный кабинет Яндекс Директа больше не подключён.")
    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")
    headers = {"Authorization": f"Bearer {token}", "Accept-Language": "ru", "Content-Type": "application/json; charset=utf-8"}
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    request_body = {"method": "add", "params": {"Ads": [{"AdGroupId": group_id, "ResponsiveAd": {"Titles": titles, "Texts": texts, "Href": href}}]}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/ads", headers=headers, json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    result = ((payload.get("result") or {}).get("AddResults") or [{}])[0]
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error or not result.get("Id"):
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не создал черновик объявления.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    ad_id = str(result["Id"])
    task_context["direct_production_release"] = {**release, "status": "direct_ads_draft_created", "direct_ad_id": ad_id, "direct_ad_type": "RESPONSIVE_AD", "direct_ad_created_at": datetime.now(timezone.utc).isoformat(), "direct_ad_copy": {"titles": titles, "texts": texts, "href": href}, "external_action": "responsive_ad_draft_created_not_moderated"}
    task.task_context = task_context
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_ads_draft_created"
    connection.last_sync_summary = {"production_group_id": str(group_id), "production_ad_id": ad_id, "message": "Создано комбинаторное объявление в статусе черновика. Модерация не запускалась, а в группе нет условий показа: показы и списания невозможны."}
    await db.commit()
    return {"status": "direct_ads_draft_created", "direct_group_id": str(group_id), "direct_ad_id": ad_id, "ad_type": "RESPONSIVE_AD", "safety": "not_moderated_and_no_targeting"}


@router.post("/traffic-projects/{task_id}/direct-production-keywords")
async def create_direct_production_keywords(
    task_id: UUID,
    body: DirectProductionKeywordsInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Add approved keywords without submitting the ads for moderation."""
    _require_ad_admin(current_user)
    if body.confirmation.strip() != "ДОБАВИТЬ КЛЮЧИ":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «ДОБАВИТЬ КЛЮЧИ».")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_ads_draft_created":
        raise HTTPException(status_code=409, detail="Сначала создайте черновик комбинаторного объявления.")
    if release.get("direct_keyword_ids"):
        raise HTTPException(status_code=409, detail="Ключевые фразы для этой группы уже добавлены. Их изменение будет отдельной операцией.")
    keywords = [str(value or "").strip() for value in body.keywords if str(value or "").strip()]
    if not 1 <= len(keywords) <= 100:
        raise HTTPException(status_code=400, detail="Укажите от 1 до 100 ключевых фраз.")
    if len(set(value.casefold() for value in keywords)) != len(keywords):
        raise HTTPException(status_code=400, detail="Удалите повторяющиеся ключевые фразы.")
    for value in keywords:
        positive_words = [word for word in value.split() if not word.startswith("-")]
        if len(value) > 4096 or len(positive_words) > 7 or any(len(word.lstrip("!-+")) > 35 for word in value.split()):
            raise HTTPException(status_code=400, detail=f"Ключевая фраза «{value}» не соответствует ограничениям Директа.")
    try:
        group_id = int(str(release.get("direct_group_id") or ""))
        connection_id = UUID(str(release.get("direct_connection_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Не найдена сохранённая группа или кабинет Директа.")
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform != "yandex_direct" or not connection.is_active or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Выбранный кабинет Яндекс Директа больше не подключён.")
    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")
    headers = {"Authorization": f"Bearer {token}", "Accept-Language": "ru", "Content-Type": "application/json; charset=utf-8"}
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    request_body = {"method": "add", "params": {"Keywords": [{"Keyword": keyword, "AdGroupId": group_id} for keyword in keywords]}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/keywords", headers=headers, json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    results = ((payload.get("result") or {}).get("AddResults") or [])
    provider_error = payload.get("error") or next((item.get("Errors", [{}])[0] for item in results if item.get("Errors")), None)
    if response.status_code >= 400 or provider_error or len(results) != len(keywords) or not all(item.get("Id") for item in results):
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не добавил ключевые фразы.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    keyword_ids = [str(item["Id"]) for item in results]
    task_context["direct_production_release"] = {**release, "status": "direct_targeting_draft_created", "direct_keyword_ids": keyword_ids, "direct_keywords": keywords, "direct_keywords_created_at": datetime.now(timezone.utc).isoformat(), "external_action": "keywords_created_ads_not_moderated"}
    task.task_context = task_context
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_keywords_created"
    connection.last_sync_summary = {"production_group_id": str(group_id), "keywords_created": len(keyword_ids), "message": "Добавлены ключевые фразы. Объявление осталось черновиком и не отправлено на модерацию; показов и списаний нет."}
    await db.commit()
    return {"status": "direct_targeting_draft_created", "direct_group_id": str(group_id), "keyword_ids": keyword_ids, "safety": "ads_not_moderated"}


def _glame_static_ad_image(url: str) -> Path:
    """Resolve a selected local media URL without accepting arbitrary server URLs."""
    clean_url = str(url or "").split("?", 1)[0]
    if not clean_url.startswith("/static/"):
        raise HTTPException(status_code=400, detail="Для импорта в Директ можно выбрать только файл, уже размещённый в медиатеке GLAME.")
    static_root = (Path(__file__).resolve().parents[2] / "static").resolve()
    candidate = (static_root / clean_url.removeprefix("/static/")).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Недопустимый путь к файлу медиатеки.")
    if not candidate.is_file() or candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif"}:
        raise HTTPException(status_code=400, detail="Директ принимает из медиатеки только существующие JPG, PNG или GIF файлы.")
    if candidate.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Файл «{candidate.name}» больше 10 МБ и не может быть загружен в Директ.")
    return candidate


async def _direct_production_connection(db: AsyncSession, release: Dict[str, Any]) -> tuple[AdvertisingConnection, str]:
    try:
        connection_id = UUID(str(release.get("direct_connection_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="В подготовке запуска не указан кабинет Яндекс Директа.")
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform != "yandex_direct" or not connection.is_active or connection.status != "connected":
        raise HTTPException(status_code=409, detail="Выбранный кабинет Яндекс Директа больше не подключён.")
    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    token = _decrypt_yandex_secret(encrypted_token or "")
    if not token:
        raise HTTPException(status_code=409, detail="Для этого кабинета требуется OAuth-авторизация владельца.")
    return connection, token


def _direct_headers(connection: AdvertisingConnection, token: str) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Accept-Language": "ru", "Content-Type": "application/json; charset=utf-8"}
    if connection.client_login:
        headers["Client-Login"] = connection.client_login
    return headers


@router.post("/traffic-projects/{task_id}/direct-production-images")
async def upload_direct_production_images(
    task_id: UUID,
    body: DirectProductionImagesInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Upload up to three GLAME-hosted media files, without attaching them to ads."""
    _require_ad_admin(current_user)
    if body.confirmation.strip() != "ЗАГРУЗИТЬ ИЗОБРАЖЕНИЯ":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «ЗАГРУЗИТЬ ИЗОБРАЖЕНИЯ».")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_targeting_draft_created":
        raise HTTPException(status_code=409, detail="Сначала создайте черновик объявления и добавьте согласованные ключевые фразы.")
    if release.get("direct_image_hashes"):
        raise HTTPException(status_code=409, detail="Изображения для этого черновика уже импортированы. Замена будет отдельной операцией.")
    local_assets = [(asset, _glame_static_ad_image(asset.url)) for asset in body.assets]
    connection, token = await _direct_production_connection(db, release)
    direct_assets = [{"ImageData": base64.b64encode(path.read_bytes()).decode("ascii"), "Name": f"GLAME {asset.title}"[:255], "Type": "AUTO"} for asset, path in local_assets]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/adimages", headers=_direct_headers(connection, token), json={"method": "add", "params": {"AdImages": direct_assets}})
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API изображений Яндекс Директа.")
    results = ((payload.get("result") or {}).get("AddResults") or [])
    provider_error = payload.get("error") or next((item.get("Errors", [{}])[0] for item in results if item.get("Errors")), None)
    if response.status_code >= 400 or provider_error or len(results) != len(direct_assets) or not all(item.get("AdImageHash") for item in results):
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не загрузил изображения.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    hashes = [str(item["AdImageHash"]) for item in results]
    task_context["direct_production_release"] = {**release, "status": "direct_images_uploaded", "direct_image_hashes": hashes, "direct_image_assets": [{"id": asset.id, "url": asset.url, "title": asset.title, "hash": image_hash} for (asset, _), image_hash in zip(local_assets, hashes)], "direct_images_uploaded_at": datetime.now(timezone.utc).isoformat(), "external_action": "images_uploaded_not_attached_or_moderated"}
    task.task_context = task_context
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_images_uploaded"
    connection.last_sync_summary = {"images_uploaded": len(hashes), "message": "Изображения загружены в библиотеку Директа, но ещё не привязаны к объявлению и не проходят модерацию."}
    await db.commit()
    return {"status": "direct_images_uploaded", "image_hashes": hashes, "safety": "not_attached_or_moderated"}


@router.post("/traffic-projects/{task_id}/direct-production-attach-images")
async def attach_direct_production_images(
    task_id: UUID,
    body: DirectProductionAttachImagesInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Attach uploaded media hashes to a ResponsiveAd that is still a DRAFT."""
    _require_ad_admin(current_user)
    if body.confirmation.strip() != "ПРИВЯЗАТЬ ИЗОБРАЖЕНИЯ":
        raise HTTPException(status_code=400, detail="Подтвердите действие фразой «ПРИВЯЗАТЬ ИЗОБРАЖЕНИЯ».")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_images_uploaded":
        raise HTTPException(status_code=409, detail="Сначала импортируйте изображения из медиатеки GLAME.")
    hashes = [str(value) for value in (release.get("direct_image_hashes") or []) if str(value)]
    if not 1 <= len(hashes) <= 5:
        raise HTTPException(status_code=409, detail="Для привязки нужно от 1 до 5 успешно импортированных изображений.")
    try:
        ad_id = int(str(release.get("direct_ad_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Черновик объявления не найден.")
    connection, token = await _direct_production_connection(db, release)
    request_body = {"method": "update", "params": {"Ads": [{"Id": ad_id, "ResponsiveAd": {"AdImageHashes": {"Items": hashes}}}]}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/ads", headers=_direct_headers(connection, token), json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
    result = ((payload.get("result") or {}).get("UpdateResults") or [{}])[0]
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error or not result.get("Id"):
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не привязал изображения к объявлению.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    task_context["direct_production_release"] = {**release, "status": "direct_images_attached", "direct_images_attached_at": datetime.now(timezone.utc).isoformat(), "external_action": "images_attached_to_draft_not_moderated"}
    task.task_context = task_context
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_images_attached"
    connection.last_sync_summary = {"production_ad_id": str(ad_id), "images_attached": len(hashes), "message": "Изображения привязаны к объявлению-черновику. Объявление не отправлено на модерацию, показы и списания невозможны."}
    await db.commit()
    return {"status": "direct_images_attached", "direct_ad_id": str(ad_id), "image_hashes": hashes, "safety": "not_moderated"}


@router.post("/traffic-projects/{task_id}/direct-production-moderation")
async def request_direct_production_moderation(
    task_id: UUID,
    body: DirectProductionModerationInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Explicitly submit a fully prepared ad draft to Direct moderation; never called by syncs or agents."""
    user = _require_ad_admin(current_user)
    if body.confirmation.strip() != "ОТПРАВИТЬ НА МОДЕРАЦИЮ" or not body.spending_acknowledged:
        raise HTTPException(status_code=400, detail="Подтвердите отправку фразой «ОТПРАВИТЬ НА МОДЕРАЦИЮ» и подтвердите понимание возможных расходов.")
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_images_attached":
        raise HTTPException(status_code=409, detail="Сначала завершите подготовку объявления, ключевых фраз и изображений.")
    if release.get("moderation_requested_at"):
        raise HTTPException(status_code=409, detail="Это объявление уже передано в Яндекс Директ на модерацию.")
    try:
        ad_id = int(str(release.get("direct_ad_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Черновик объявления не найден.")
    keyword_ids = [str(value) for value in (release.get("direct_keyword_ids") or []) if str(value)]
    image_hashes = [str(value) for value in (release.get("direct_image_hashes") or []) if str(value)]
    if not keyword_ids or not image_hashes:
        raise HTTPException(status_code=409, detail="Для модерации нужны добавленные ключевые фразы и привязанные изображения.")
    connection, token = await _direct_production_connection(db, release)
    request_body = {"method": "moderate", "params": {"SelectionCriteria": {"Ids": [ad_id]}}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/ads", headers=_direct_headers(connection, token), json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось связаться с API модерации Яндекс Директа.")
    results = ((payload.get("result") or {}).get("ModerateResults") or [{}])
    result = results[0] if results else {}
    provider_error = payload.get("error") or ((result.get("Errors") or [{}])[0] if isinstance(result, dict) else {})
    if response.status_code >= 400 or provider_error:
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не принял запрос на модерацию.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    now = datetime.now(timezone.utc).isoformat()
    audit_event = {
        "action": "direct_ads_moderate_requested",
        "at": now,
        "ad_id": str(ad_id),
        "campaign_id": str(release.get("direct_campaign_id") or ""),
        "group_id": str(release.get("direct_group_id") or ""),
        "keyword_ids": keyword_ids,
        "image_hashes": image_hashes,
        "confirmation": "ОТПРАВИТЬ НА МОДЕРАЦИЮ",
        "spending_acknowledged": True,
        "user_id": str(user.id),
        "user_email": getattr(user, "email", None),
    }
    task_context["direct_production_release"] = {**release, "status": "direct_moderation_requested", "moderation_requested_at": now, "moderation_requested_by": str(user.id), "external_action": "ads_moderate_requested"}
    task_context["direct_launch_audit"] = [*(task_context.get("direct_launch_audit") or []), audit_event]
    task.task_context = task_context
    db.add(AgentInteractionLog(task_id=task.id, agent_name="traffic-growth-agent", event_type="direct_moderation_requested", event_data=audit_event, message="Пользователь подтвердил отправку объявления Яндекс Директа на модерацию."))
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "production_moderation_requested"
    connection.last_sync_summary = {"production_ad_id": str(ad_id), "message": "Объявление передано в Яндекс Директ на модерацию по явному подтверждению администратора."}
    await db.commit()
    return {"status": "direct_moderation_requested", "direct_ad_id": str(ad_id), "safety": "moderation_requested_by_explicit_admin_confirmation"}


@router.get("/traffic-projects/{task_id}/direct-production-moderation-status")
async def get_direct_production_moderation_status(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Read the provider's state for a submitted draft; does not alter Direct settings or budgets."""
    _require_ad_admin(current_user)
    task = await db.get(AgentInteractionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Рекламный проект не найден.")
    task_context = dict(task.task_context or {})
    release = task_context.get("direct_production_release")
    if not isinstance(release, dict) or release.get("status") != "direct_moderation_requested":
        raise HTTPException(status_code=409, detail="Проверка доступна после явной отправки объявления на модерацию.")
    try:
        ad_id = int(str(release.get("direct_ad_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Черновик объявления не найден.")
    connection, token = await _direct_production_connection(db, release)
    request_body = {"method": "get", "params": {"SelectionCriteria": {"Ids": [ad_id]}, "FieldNames": ["Id", "State", "Status", "StatusClarification"]}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.direct.yandex.com/json/v501/ads", headers=_direct_headers(connection, token), json=request_body)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Не удалось получить статус из API Яндекс Директа.")
    provider_error = payload.get("error")
    ads = ((payload.get("result") or {}).get("Ads") or [])
    if response.status_code >= 400 or provider_error or not ads:
        raise HTTPException(status_code=502, detail={"message": (provider_error or {}).get("error_string") or (provider_error or {}).get("Message") or "Яндекс Директ не вернул статус объявления.", "provider_code": (provider_error or {}).get("error_code") or (provider_error or {}).get("Code") or response.status_code})
    remote = ads[0]
    checked_at = datetime.now(timezone.utc).isoformat()
    moderation = {"checked_at": checked_at, "id": str(remote.get("Id") or ad_id), "state": remote.get("State"), "status": remote.get("Status"), "clarification": remote.get("StatusClarification")}
    task_context["direct_production_release"] = {**release, "direct_moderation_last_check": moderation}
    task.task_context = task_context
    await db.commit()
    return {"status": "direct_moderation_requested", "moderation": moderation, "safety": "read_only"}


@router.post("/advertising-connections/{connection_id}/sync")
async def sync_advertising_connection(
    connection_id: UUID,
    body: AdvertisingConnectionSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Run a read-only import. No Direct write methods are called from this endpoint."""
    user = _require_ad_admin(current_user)
    item = await db.get(AdvertisingConnection, connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Кабинет не найден")
    if not item.is_active:
        raise HTTPException(status_code=409, detail="Кабинет отключён. Сначала включите его в реестре.")
    client_id, client_secret = await _yandex_oauth_settings(db)
    if not client_id or not client_secret:
        item.status = "awaiting_oauth"
        item.last_sync_status = "not_configured"
        item.last_sync_summary = {
            "campaigns_imported": 0,
            "message": "В платформе ещё не заполнены Client ID и Client secret OAuth-приложения Яндекса.",
        }
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail="Синхронизация недоступна: заполните Client ID и Client secret OAuth-приложения Яндекса.",
        )
    encrypted_token = await _get_app_setting(db, f"yandex_oauth_token_{connection_id}")
    if not encrypted_token or not _decrypt_yandex_secret(encrypted_token):
        item.status = "awaiting_account_authorization"
        item.last_sync_status = "authorization_required"
        item.last_sync_summary = {
            "campaigns_imported": 0,
            "message": "Для этого кабинета требуется завершить OAuth-авторизацию владельца аккаунта.",
            "force": body.force,
        }
    else:
        if item.platform != "yandex_direct":
            raise HTTPException(status_code=409, detail="Для этой площадки read-only адаптер ещё не подключён.")
        try:
            imported = await _sync_yandex_direct_campaigns(db, item, _decrypt_yandex_secret(encrypted_token), user)
            metrics = await _sync_yandex_direct_daily_metrics(db, item, _decrypt_yandex_secret(encrypted_token))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            item.last_sync_status = "api_error"
            item.last_sync_summary = {"campaigns_imported": 0, "message": detail.get("message", "Ошибка API Яндекс Директа"), "provider_code": detail.get("provider_code")}
            await db.commit()
            raise
        except httpx.HTTPError:
            item.last_sync_status = "network_error"
            item.last_sync_summary = {"campaigns_imported": 0, "message": "Не удалось связаться с API Яндекс Директа. Повторите синхронизацию позже."}
            await db.commit()
            raise HTTPException(status_code=502, detail="Не удалось связаться с API Яндекс Директа.")
        item.status = "connected"
        item.last_sync_at = datetime.now(timezone.utc)
        item.last_sync_status = "success"
        item.last_sync_summary = {
            "campaigns_imported": imported["received"],
            "created": imported["created"],
            "updated": imported["updated"],
            "metric_rows": metrics["upserted"],
            "metrics_pending": metrics["pending"],
            "mode": "read_only",
            "message": (
                f"Импортировано кампаний: {imported['received']}. Новых: {imported['created']}, обновлено: {imported['updated']}. "
                + ("Отчёт по метрикам готовится в Яндексе — повторите синхронизацию через несколько минут." if metrics["pending"] else f"Загружено дневных строк метрик: {metrics['upserted']}.")
            ),
        }
    await db.commit(); await db.refresh(item)
    return _connection_payload(item, bool(client_id and client_secret))


@router.get("/advertising-analytics")
async def advertising_analytics(
    days: int = Query(14, ge=1, le=90),
    connection_id: Optional[UUID] = None,
    metrika_counter_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Aggregated, read-only advertising facts for the Traffic & Growth Board."""
    _require_ad_admin(current_user)
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    statement = select(AdvertisingDailyMetric).where(AdvertisingDailyMetric.metric_date >= since)
    if connection_id:
        statement = statement.where(AdvertisingDailyMetric.advertising_connection_id == connection_id)
    rows = (await db.execute(statement.order_by(AdvertisingDailyMetric.metric_date.asc()))).scalars().all()
    connection_ids = {row.advertising_connection_id for row in rows}
    connections = {
        item.id: item
        for item in (await db.execute(select(AdvertisingConnection).where(AdvertisingConnection.id.in_(connection_ids)))).scalars().all()
    } if connection_ids else {}
    row_campaign_ids = {row.marketing_campaign_id for row in rows if row.marketing_campaign_id}
    row_campaign_map = {
        item.id: item
        for item in (await db.execute(select(MarketingCampaign).where(MarketingCampaign.id.in_(row_campaign_ids)))).scalars().all()
    } if row_campaign_ids else {}
    if metrika_counter_id:
        # Business/Maps sources are bound per connection; Direct is bound per
        # campaign because a single advertiser account can contain many stores.
        rows = [row for row in rows if (
            str(((connections.get(row.advertising_connection_id).permissions if connections.get(row.advertising_connection_id) else {}) or {}).get("metrika_counter_id") or "") == metrika_counter_id
            if connections.get(row.advertising_connection_id) and connections[row.advertising_connection_id].platform in {"yandex_business", "yandex_maps"}
            else str(((row_campaign_map.get(row.marketing_campaign_id).metrics if row_campaign_map.get(row.marketing_campaign_id) else {}) or {}).get("metrika_counter_id") or "") == metrika_counter_id
        )]
    campaign_ids = {row.marketing_campaign_id for row in rows if row.marketing_campaign_id}
    campaign_map = {campaign_id: row_campaign_map[campaign_id] for campaign_id in campaign_ids if campaign_id in row_campaign_map}
    grouped: Dict[str, Dict[str, Any]] = {}
    totals = {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}
    business_ad_totals = {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}
    business_campaign_facts = {"card_opens": 0, "routes": 0, "calls": 0, "messages": 0, "website_clicks": 0}
    business_stores: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        connection = connections.get(row.advertising_connection_id)
        if connection and connection.platform in {"yandex_business", "yandex_maps"}:
            store = business_stores.setdefault(str(connection.id), {
                "connection_id": str(connection.id), "store_name": connection.name,
                "days": 0, "card_opens": 0, "routes": 0, "calls": 0, "messages": 0, "website_clicks": 0,
            })
            store["days"] += 1
            for field, value in _business_maps_raw_metrics(row).items():
                business_campaign_facts[field] += value
                store[field] += value
            for field in business_ad_totals:
                business_ad_totals[field] += getattr(row, field) or 0
            continue
        key = f"{row.advertising_connection_id}:{row.external_campaign_id}"
        campaign = campaign_map.get(row.marketing_campaign_id)
        target = grouped.setdefault(key, {
            "connection_id": str(row.advertising_connection_id),
            "external_campaign_id": row.external_campaign_id,
            "campaign_id": str(row.marketing_campaign_id) if row.marketing_campaign_id else None,
            "campaign_name": campaign.name if campaign else f"Яндекс Директ #{row.external_campaign_id}",
            "impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0,
        })
        for field in totals:
            target[field] += getattr(row, field) or 0
            totals[field] += getattr(row, field) or 0
    for field in totals:
        totals[field] += business_ad_totals[field]
    for item in grouped.values():
        item["ctr"] = round((item["clicks"] / item["impressions"] * 100), 2) if item["impressions"] else 0.0
        item["cpc"] = round((item["cost"] / item["clicks"]), 2) if item["clicks"] else 0.0
    totals["ctr"] = round((totals["clicks"] / totals["impressions"] * 100), 2) if totals["impressions"] else 0.0
    totals["cpc"] = round((totals["cost"] / totals["clicks"]), 2) if totals["clicks"] else 0.0
    metrika_counters = await _yandex_metrika_counters(db)
    if metrika_counter_id:
        metrika_counters = [item for item in metrika_counters if item["id"] == metrika_counter_id]
        if not metrika_counters:
            raise HTTPException(status_code=404, detail="Счётчик Метрики для выбранного магазина не найден.")
    metrika: Dict[str, Any] = {"status": "not_configured", "message": "Нужны ID счётчика и OAuth-токен Метрики."}
    if metrika_counters:
        counter_results: List[Dict[str, Any]] = []
        metrika_organization_actions = {"card_opens": 0, "routes": 0, "calls": 0, "route_starts": 0, "messages": 0, "website_clicks": 0}
        for counter in metrika_counters:
            try:
                async with YandexMetrikaService(counter_id=counter["counter_id"], oauth_token=counter["oauth_token"]) as service:
                    start_at = datetime.now(timezone.utc) - timedelta(days=days - 1)
                    visits_data = await service.get_visits_metrics(start_at, datetime.now(timezone.utc))
                    try:
                        organization_actions = await service.get_organization_actions(start_at, datetime.now(timezone.utc))
                    except Exception:
                        # A counter may be a regular website counter or an OAuth token may
                        # not have Management API access. Keep its visits available.
                        organization_actions = {"is_organization_counter": False, "card_opens": 0, "routes": 0, "calls": 0, "route_starts": 0, "messages": 0, "website_clicks": 0, "recognized_goals": []}
                    if organization_actions["is_organization_counter"]:
                        for field in metrika_organization_actions:
                            metrika_organization_actions[field] += int(organization_actions.get(field) or 0)
                    counter_results.append({**_metrika_counter_payload(counter), "status": "ready", "data": visits_data, "organization_actions": organization_actions})
            except Exception:
                counter_results.append({**_metrika_counter_payload(counter), "status": "error"})
        ready = [item for item in counter_results if item["status"] == "ready"]
        metrika = {
            "status": "ready" if ready else "error",
            "data": {"visits": sum(int((item.get("data") or {}).get("visits") or 0) for item in ready)},
            "counters": counter_results,
            "organization_actions": metrika_organization_actions,
            "message": f"Подключено счётчиков Метрики: {len(ready)} из {len(counter_results)}.",
        }
    else:
        metrika_organization_actions = {"card_opens": 0, "routes": 0, "calls": 0, "route_starts": 0, "messages": 0, "website_clicks": 0}
    maps_connections = (await db.execute(
        select(AdvertisingConnection).where(AdvertisingConnection.platform.in_(["yandex_business", "yandex_maps"]))
    )).scalars().all()
    maps_status = "ready" if any(business_campaign_facts.values()) else ("awaiting_input" if maps_connections else "not_connected")
    return {
        "period_days": days,
        "scope": {"metrika_counter_id": metrika_counter_id, "mode": "store" if metrika_counter_id else "all"},
        "freshness": max((row.imported_at for row in rows if row.imported_at), default=None),
        "totals": totals,
        "campaigns": sorted(grouped.values(), key=lambda item: item["cost"], reverse=True),
        "funnel": {
            "impressions": totals["impressions"], "clicks": totals["clicks"],
            "card_opens": metrika_organization_actions["card_opens"], "routes": metrika_organization_actions["routes"], "calls": metrika_organization_actions["calls"],
            "website_visits": int((metrika.get("data") or {}).get("visits") or 0),
            "conversions": totals["conversions"],
        },
        "maps_facts": business_campaign_facts,
        "business_stores": sorted(business_stores.values(), key=lambda item: item["store_name"]),
        "business_ad_totals": business_ad_totals,
        "metrika_organization_actions": metrika_organization_actions,
        "metrika_counters": metrika.get("counters", []),
        "sources": {
            "yandex_direct": {"status": "ready" if any(connections.get(row.advertising_connection_id) and connections[row.advertising_connection_id].platform == "yandex_direct" for row in rows) else "no_data", "message": "Дневные показы, клики и расход из read-only API Яндекс Директа."},
            "yandex_business_maps": {"status": maps_status, "message": "Рекламные показатели и коллтрекинг Яндекс Бизнеса: импорт из кабинета без смешивания с органикой."},
            "yandex_metrika": {"status": metrika["status"], "message": metrika.get("message") or "Посещения и автоматические цели карточек получены через Reporting API Метрики."},
        },
    }


@router.post("/advertising-analytics/yandex-business-maps-daily")
async def save_yandex_business_maps_daily_metrics(
    body: YandexBusinessMapsDailyMetricsInput,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Store a manually verified daily snapshot from the Business/Maps cabinet."""
    _require_ad_admin(current_user)
    connection = await db.get(AdvertisingConnection, body.connection_id)
    if not connection or connection.platform not in {"yandex_business", "yandex_maps"}:
        raise HTTPException(status_code=400, detail="Выберите подключение Яндекс Бизнес или Яндекс Карт.")
    values = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    metrics = {key: int(values[key] or 0) for key in ("card_opens", "routes", "calls", "messages", "website_clicks")}
    existing = (await db.execute(select(AdvertisingDailyMetric).where(
        AdvertisingDailyMetric.advertising_connection_id == connection.id,
        AdvertisingDailyMetric.external_campaign_id == "business_card",
        AdvertisingDailyMetric.metric_date == body.metric_date,
    ))).scalar_one_or_none()
    raw_metrics = {"source": "yandex_business_maps_manual", **metrics}
    if existing:
        existing.raw_metrics = raw_metrics
        existing.imported_at = datetime.now(timezone.utc)
    else:
        db.add(AdvertisingDailyMetric(
            advertising_connection_id=connection.id,
            external_campaign_id="business_card",
            metric_date=body.metric_date,
            impressions=0, clicks=0, cost=0.0, conversions=0.0,
            raw_metrics=raw_metrics,
        ))
    await db.commit()
    return {"status": "saved", "metric_date": body.metric_date.isoformat(), "metrics": metrics}


@router.post("/advertising-analytics/yandex-business-maps-import")
async def import_yandex_business_maps_statistics(
    connection_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Import a daily Excel/CSV export from one Yandex Business store campaign."""
    _require_ad_admin(current_user)
    connection = await db.get(AdvertisingConnection, connection_id)
    if not connection or connection.platform not in {"yandex_business", "yandex_maps"}:
        raise HTTPException(status_code=400, detail="Выберите подключённый магазин Яндекс Бизнес или Карт.")
    filename = file.filename or "statistics"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"xlsx", "xls", "csv"}:
        raise HTTPException(status_code=400, detail="Поддерживаются выгрузки Яндекс Бизнес в XLSX, XLS или CSV.")
    content = await file.read()
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл пустой или превышает 15 МБ.")
    try:
        is_yandex_html_xls = suffix == "xls" and content.lstrip().lower().startswith((b"<html", b"<!doctype html"))
        if is_yandex_html_xls:
            frame = _parse_yandex_business_html_export(content)
        elif suffix == "csv":
            frame = pd.read_csv(io.BytesIO(content), sep=None, engine="python")
        else:
            frame = pd.read_excel(io.BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось прочитать выгрузку. Скачайте таблицу из Яндекс Бизнес в XLSX или CSV и повторите.")
    if frame.empty:
        raise HTTPException(status_code=400, detail="В файле нет строк статистики.")
    date_column = _business_metrics_column(list(frame.columns), ["дата", "date"])
    if not date_column:
        raise HTTPException(status_code=400, detail="В выгрузке не найдена колонка «Дата». Выберите детализацию по дням перед скачиванием отчёта.")
    metric_columns = {
        "impressions": _business_metrics_column(list(frame.columns), ["impressions", "просмотры рекламы", "показы рекламы", "показы"]),
        "clicks": _business_metrics_column(list(frame.columns), ["clicks", "переходы по рекламе", "клики по рекламе", "переходы"]),
        "cost": _business_metrics_column(list(frame.columns), ["cost", "расход", "затраты", "стоимость"]),
        "conversions": _business_metrics_column(list(frame.columns), ["conversions", "целевых действий", "целевые действия"]),
        "card_opens": _business_metrics_column(list(frame.columns), ["card_opens", "переходы в профиль", "посещения профиля", "просмотры профиля", "открытия карточки", "профиль компании"]),
        "routes": _business_metrics_column(list(frame.columns), ["routes", "маршрут", "построение маршрута"]),
        "calls": _business_metrics_column(list(frame.columns), ["calls", "звонк", "телефон"]),
        "messages": _business_metrics_column(list(frame.columns), ["messages", "сообщени"]),
        "website_clicks": _business_metrics_column(list(frame.columns), ["website_clicks", "переходы на сайт", "клики на сайт", "сайт"]),
    }
    if not any(metric_columns.values()):
        raise HTTPException(status_code=400, detail="Не распознаны показатели. В отчёте должны быть рекламные показы/переходы или действия в профиле: маршрут, телефон, сайт.")
    created = updated = skipped = 0
    for _, row in frame.iterrows():
        parsed_date = pd.to_datetime(row.get(date_column), errors="coerce")
        if pd.isna(parsed_date):
            skipped += 1
            continue
        metric_date = parsed_date.date()
        provided_metrics = {
            name: _business_metrics_number(row.get(column))
            for name, column in metric_columns.items()
            if column is not None
        }
        existing = (await db.execute(select(AdvertisingDailyMetric).where(
            AdvertisingDailyMetric.advertising_connection_id == connection.id,
            AdvertisingDailyMetric.external_campaign_id == "business_card",
            AdvertisingDailyMetric.metric_date == metric_date,
        ))).scalar_one_or_none()
        if existing:
            previous_raw = dict(existing.raw_metrics or {})
            metrics = {
                "impressions": int(existing.impressions or 0),
                "clicks": int(existing.clicks or 0),
                "cost": float(existing.cost or 0),
                "conversions": float(existing.conversions or 0),
                **_business_maps_raw_metrics(existing),
                **provided_metrics,
            }
            raw_metrics = {
                **previous_raw,
                "source": "yandex_business_excel",
                "filenames": list(dict.fromkeys([*(previous_raw.get("filenames") or [previous_raw.get("filename")] if previous_raw.get("filename") else []), filename])),
                **metrics,
            }
            existing.impressions = metrics["impressions"]
            existing.clicks = metrics["clicks"]
            existing.cost = float(metrics["cost"])
            existing.conversions = float(metrics["conversions"])
            existing.raw_metrics = raw_metrics
            existing.imported_at = datetime.now(timezone.utc)
            updated += 1
        else:
            metrics = {
                "impressions": 0,
                "clicks": 0,
                "cost": 0.0,
                "conversions": 0.0,
                "card_opens": 0,
                "routes": 0,
                "calls": 0,
                "messages": 0,
                "website_clicks": 0,
                **provided_metrics,
            }
            raw_metrics = {"source": "yandex_business_excel", "filenames": [filename], **metrics}
            db.add(AdvertisingDailyMetric(advertising_connection_id=connection.id, external_campaign_id="business_card", metric_date=metric_date, impressions=metrics["impressions"], clicks=metrics["clicks"], cost=float(metrics["cost"]), conversions=float(metrics["conversions"]), raw_metrics=raw_metrics))
            created += 1
    await db.commit()
    return {"status": "imported", "connection_id": str(connection_id), "filename": filename, "created": created, "updated": updated, "skipped": skipped, "recognized_columns": {name: str(column) if column else None for name, column in metric_columns.items()}}


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Парсинг ISO datetime строки"""
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {dt_str}")


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(
    campaign: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Создание новой маркетинговой кампании"""
    try:
        service = CampaignService(db)
        
        new_campaign = await service.create_campaign(
            name=campaign.name,
            campaign_type=campaign.type,
            start_date=_parse_iso_datetime(campaign.start_date),
            end_date=_parse_iso_datetime(campaign.end_date) if campaign.end_date else None,
            user_id=current_user.id if current_user else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=UUID(campaign.content_plan_id) if campaign.content_plan_id else None
        )
        
        return CampaignResponse(
            id=str(new_campaign.id),
            name=new_campaign.name,
            type=new_campaign.type,
            status=new_campaign.status,
            start_date=new_campaign.start_date.isoformat(),
            end_date=new_campaign.end_date.isoformat() if new_campaign.end_date else None,
            budget=new_campaign.budget,
            target_audience=new_campaign.target_audience,
            channels=new_campaign.channels,
            content_plan_id=str(new_campaign.content_plan_id) if new_campaign.content_plan_id else None,
            metrics=new_campaign.metrics,
            external_source=new_campaign.external_source,
            external_id=new_campaign.external_id,
            advertising_connection_id=str(new_campaign.advertising_connection_id) if new_campaign.advertising_connection_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating campaign: {str(e)}")


@router.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    status: Optional[str] = None,
    campaign_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Список маркетинговых кампаний"""
    try:
        service = CampaignService(db)
        campaigns = await service.list_campaigns(
            user_id=current_user.id if current_user else None,
            status=status,
            campaign_type=campaign_type
        )
        
        return [
            CampaignResponse(
                id=str(c.id),
                name=c.name,
                type=c.type,
                status=c.status,
                start_date=c.start_date.isoformat(),
                end_date=c.end_date.isoformat() if c.end_date else None,
                budget=c.budget,
                target_audience=c.target_audience,
                channels=c.channels,
                content_plan_id=str(c.content_plan_id) if c.content_plan_id else None,
                metrics=c.metrics,
                external_source=c.external_source,
                external_id=c.external_id,
                advertising_connection_id=str(c.advertising_connection_id) if c.advertising_connection_id else None,
            )
            for c in campaigns
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing campaigns: {str(e)}")


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Получение кампании по ID"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not current_user and campaign.user_id is not None:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            type=campaign.type,
            status=campaign.status,
            start_date=campaign.start_date.isoformat(),
            end_date=campaign.end_date.isoformat() if campaign.end_date else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=str(campaign.content_plan_id) if campaign.content_plan_id else None,
            metrics=campaign.metrics,
            external_source=campaign.external_source,
            external_id=campaign.external_id,
            advertising_connection_id=str(campaign.advertising_connection_id) if campaign.advertising_connection_id else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting campaign: {str(e)}")


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    campaign_update: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Обновление кампании"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not current_user and campaign.user_id is not None:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if campaign_update.name:
            campaign.name = campaign_update.name
        if campaign_update.status:
            await service.update_campaign_status(campaign_id, campaign_update.status)
        if campaign_update.budget is not None:
            campaign.budget = campaign_update.budget
        if campaign_update.target_audience:
            campaign.target_audience = campaign_update.target_audience
        if campaign_update.channels:
            campaign.channels = campaign_update.channels
        
        campaign.updated_at = datetime.now()
        await db.commit()
        await db.refresh(campaign)
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            type=campaign.type,
            status=campaign.status,
            start_date=campaign.start_date.isoformat(),
            end_date=campaign.end_date.isoformat() if campaign.end_date else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=str(campaign.content_plan_id) if campaign.content_plan_id else None,
            metrics=campaign.metrics,
            external_source=campaign.external_source,
            external_id=campaign.external_id,
            advertising_connection_id=str(campaign.advertising_connection_id) if campaign.advertising_connection_id else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating campaign: {str(e)}")


@router.post("/campaigns/{campaign_id}/analyze")
async def analyze_campaign(
    campaign_id: UUID,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Анализ эффективности кампании"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        agent = MarketingAgent(db)
        
        start = _parse_iso_datetime(start_date) if start_date else campaign.start_date
        end = _parse_iso_datetime(end_date) if end_date else (campaign.end_date or datetime.now())
        
        analysis = await agent.analyze_campaign_performance(
            campaign_id=str(campaign_id),
            start_date=start,
            end_date=end,
            channel=campaign.channels[0] if campaign.channels else None
        )
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing campaign: {str(e)}")


@router.post("/campaigns/{campaign_id}/optimize")
async def optimize_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Оптимизация кампании"""
    try:
        service = CampaignService(db)
        optimization = await service.optimize_campaign(campaign_id)
        return optimization
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing campaign: {str(e)}")


@router.get("/campaigns/{campaign_id}/monitor")
async def monitor_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Мониторинг метрик кампании"""
    try:
        service = CampaignService(db)
        metrics = await service.monitor_campaign(campaign_id)
        return metrics
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error monitoring campaign: {str(e)}")


@router.post("/suggest-strategy")
async def suggest_strategy(
    goal: str,
    target_audience: Optional[str] = None,
    budget: Optional[float] = None,
    timeframe: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Предложение стратегии кампании"""
    try:
        agent = MarketingAgent(db)
        strategy = await agent.suggest_campaign_strategy(
            goal=goal,
            target_audience=target_audience,
            budget=budget,
            timeframe=timeframe
        )
        return strategy
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error suggesting strategy: {str(e)}")


@router.post("/predict-engagement")
async def predict_engagement(
    content_type: str,
    channel: str,
    topic: Optional[str] = None,
    persona: Optional[str] = None,
    cjm_stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Предсказание вовлеченности для контента"""
    try:
        agent = MarketingAgent(db)
        prediction = await agent.predict_engagement(
            content_type=content_type,
            channel=channel,
            topic=topic,
            persona=persona,
            cjm_stage=cjm_stage
        )
        return prediction
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting engagement: {str(e)}")


@router.post("/optimize-plan")
async def optimize_content_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Оптимизация контент-плана"""
    try:
        agent = MarketingAgent(db)
        optimization = await agent.optimize_content_plan(plan_id=plan_id)
        return optimization
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing plan: {str(e)}")


@router.post("/campaigns/auto-start")
async def auto_start_campaigns(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Автоматический запуск кампаний (фоновый процесс)"""
    try:
        service = CampaignService(db)
        background_tasks.add_task(service.auto_start_campaigns)
        return {"status": "accepted", "message": "Auto-start task started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting auto-start task: {str(e)}")


@router.post("/campaigns/auto-stop")
async def auto_stop_campaigns(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Автоматическая остановка кампаний (фоновый процесс)"""
    try:
        service = CampaignService(db)
        background_tasks.add_task(service.auto_stop_campaigns)
        return {"status": "accepted", "message": "Auto-stop task started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting auto-stop task: {str(e)}")


class DashboardResponse(BaseModel):
    pending_approvals: int
    active_tasks: int
    completed_today: int
    tomorrow_plan_ready: bool

    class Config:
        from_attributes = True


@router.get("/ai-marketer/dashboard", response_model=DashboardResponse)
async def get_ai_marketer_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """API эндпоинт для получения реальных данных дашборда AI Marketing Director (замена заглушки)"""
    from sqlalchemy import select, func
    from app.models.agent_interaction import AgentInteractionTask, InteractionStatus
    
    # Подсчитываем ожидающие согласования задачи (в статусе pending_approval)
    pending_query = select(func.count()).select_from(AgentInteractionTask).where(
        AgentInteractionTask.status == InteractionStatus.PENDING_APPROVAL.value
    )
    if current_user:
        # source_agent is a string agent identifier, while current_user.id is a UUID.
        # Cast the user id before comparing so PostgreSQL does not try to compare
        # varchar <> uuid.
        pending_query = pending_query.where(AgentInteractionTask.source_agent != str(current_user.id))
    pending_res = await db.execute(pending_query)
    pending_approvals = pending_res.scalar() or 0
    
    # Подсчитываем активные задачи
    active_query = select(func.count()).select_from(AgentInteractionTask).where(
        AgentInteractionTask.status.in_([
            InteractionStatus.PROCESSING.value,
            InteractionStatus.QUEUED.value
        ])
    )
    active_res = await db.execute(active_query)
    active_tasks = active_res.scalar() or 0
    
    # Подсчитываем завершенные за сегодня задачи
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_query = select(func.count()).select_from(AgentInteractionTask).where(
        AgentInteractionTask.status == InteractionStatus.COMPLETED.value,
        AgentInteractionTask.completed_at >= today_start
    )
    completed_res = await db.execute(completed_query)
    completed_today = completed_res.scalar() or 0
    
    # Проверяем, готов ли план на завтра
    # Ищем задачу с планом на завтра, которая помечена как готовая к согласованию
    tomorrow_plan_ready = False
    plan_query = select(AgentInteractionTask).where(
        AgentInteractionTask.task_type == "tomorrow_plan_preparation",
        AgentInteractionTask.status == InteractionStatus.COMPLETED.value
    ).order_by(AgentInteractionTask.created_at.desc()).limit(1)
    plan_res = await db.execute(plan_query)
    plan_task = plan_res.scalar_one_or_none()
    if plan_task and (datetime.utcnow() - plan_task.completed_at).total_seconds() < 86400:
        tomorrow_plan_ready = True
    
    return DashboardResponse(
        pending_approvals=pending_approvals,
        active_tasks=active_tasks,
        completed_today=completed_today,
        tomorrow_plan_ready=tomorrow_plan_ready
    )
