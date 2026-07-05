"""
API endpoints для межагентного взаимодействия.
Включает создание задач, валидацию, приоритизацию и логирование.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, and_, func, or_, text as sql_text
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
import logging
import re
import json
import os
import hashlib
from pathlib import Path

from app.database.connection import get_db
from app.api.auth import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.agent_interaction import (
    AgentInteractionTask,
    AgentInteractionLog,
    AgentValidationRule,
    AgentContentHandoff,
    InteractionStatus,
    TaskPriority
)
from app.models.agent_system_prompt import AgentSystemPrompt
from app.agents.advanced_content_agent import AdvancedContentAgent
from app.services.agent_interaction_service import AgentInteractionService
from app.agents.communication_agent import CommunicationAgent
from app.agents.marketing_agent import MarketingAgent
from app.agents.inventory_procurement_agent import InventoryProcurementAgent
from app.agents.inventory_control_agent import InventoryControlAgent
from app.agents.inventory_clearance_agent import ClearanceAgent
from app.agents.inventory_assortment_matrix_agent import AssortmentMatrixAgent
from app.agents.inventory_merchandising_agent import MerchandisingAgent
from app.agents.inventory_pricing_agent import PricingAgent
from app.agents.director_data_service import DirectorDataService
from app.services.communication_service import CommunicationService
from app.services.vector_service import vector_service
from app.services.vector_service import delete_task_dialog_by_log_id
from app.services.llm_service import llm_service
from app.services.ai_core_runtime import generate_agent_text
from app.services.hermes_web_ui_mirror import mirror_agent_task_turn_to_hermes_web_ui
from app.models.customer_message import CustomerMessage
from app.agents.contracts import prompt_agent_id
from app.services.agent_execution_dispatcher import agent_execution_dispatcher, resolve_execution_agent_id
from app.services.hermes_task_execution_service import HermesTaskExecutionService
import uuid

router = APIRouter(tags=["agent-interactions"])
logger = logging.getLogger(__name__)


def _execution_agent_id(agent_id: str) -> str:
    return resolve_execution_agent_id(agent_id)


def _prompt_agent_id(agent_id: str) -> str:
    return prompt_agent_id(agent_id)


AGENT_IDENTITY_TEXT: Dict[str, str] = {
    "director-agent": (
        "Я — AI Marketing Director GLAME, главный агент-оркестратор платформы. "
        "Я принимаю задачи от администратора, распределяю работу между профильными AI-агентами, "
        "контролирую выполнение и возвращаю результат на согласование."
    ),
    "crm-agent": (
        "Я — AI CRM GLAME, агент клиентских коммуникаций. "
        "Я собираю и проверяю сегменты покупателей, готовлю сценарии рассылок, "
        "контролирую согласия, каналы и результат CRM-задач."
    ),
    "assortment-agent": (
        "Я — AI Assortment GLAME, агент ассортимента. "
        "Я работаю с товарами, остатками, продажами, product focus и задачами по ассортиментной матрице."
    ),
    "analytics-agent": (
        "Я — AI Analytics GLAME, аналитический агент. "
        "Я собираю данные по продажам, чекам, посещениям, сайту, приложению и готовлю отчёты для решений."
    ),
    "brand-media-agent": (
        "Я — AI Brand Media GLAME, агент бренд-контента. "
        "Я готовлю контентные идеи, тексты, медиапланы и материалы для коммуникаций бренда."
    ),
    "personal-media-agent": (
        "Я — AI Personal Media GLAME, агент личного медиа Елены. "
        "Я помогаю вести личный контент, экспертность, tone of voice и план публикаций."
    ),
    "traffic-growth-agent": (
        "Я — AI Traffic & Growth GLAME, агент роста и трафика. "
        "Я планирую гипотезы привлечения, воронки, каналы и эксперименты роста."
    ),
    "pr-partnerships-agent": (
        "Я — AI PR & Partnerships GLAME, агент PR и партнёрств. "
        "Я готовлю партнёрские сценарии, PR-поводы, коллаборации и коммуникации."
    ),
}


def _is_agent_identity_question(message: str) -> bool:
    normalized = re.sub(r"[?!.,:;\"'«»()\[\]{}]+", " ", (message or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    return normalized in {
        "ты кто",
        "кто ты",
        "вы кто",
        "кто вы",
        "представься",
        "расскажи кто ты",
        "что ты за агент",
        "какой ты агент",
    }


def _agent_identity_reply(agent_id: str) -> str:
    canonical = _prompt_agent_id(agent_id)
    return AGENT_IDENTITY_TEXT.get(
        canonical,
        "Я — профильный AI-агент GLAME. Я работаю в своей зоне ответственности, отвечаю в рабочем чате задачи и передаю результат директору или администратору.",
    )


SEGMENT_CONTEXT_STALE_KEYS = {
    "segment_refinement",
    "segment_initial_customer_count",
    "segment_target_size",
    "target_applied",
}


ALLOWED_TASK_ARTIFACT_DIRS = (
    Path("/workspace/glame-platform/reports"),
    Path("/workspace/glame-platform/artifacts"),
    Path("/root/glame-platform/reports"),
    Path("/root/glame-platform/artifacts"),
)


def _is_path_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_local_artifact_path(raw_path: Optional[str]) -> Optional[Path]:
    if not raw_path:
        return None
    path_text = str(raw_path).strip()
    if not path_text:
        return None
    candidates: List[Path] = []
    raw_candidate = Path(path_text)
    if raw_candidate.is_absolute():
        candidates.append(raw_candidate)
    if path_text.startswith("/workspace/glame-platform/"):
        candidates.append(Path(path_text.replace("/workspace/glame-platform/", "/root/glame-platform/", 1)))
    if not raw_candidate.is_absolute():
        for allowed_dir in ALLOWED_TASK_ARTIFACT_DIRS:
            candidates.append(allowed_dir / path_text)
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            if not resolved.is_file():
                continue
            for allowed_dir in ALLOWED_TASK_ARTIFACT_DIRS:
                try:
                    allowed_resolved = allowed_dir.resolve(strict=True)
                except OSError:
                    continue
                if _is_path_relative_to(resolved, allowed_resolved):
                    return resolved
        except OSError:
            continue
    return None


def _read_task_artifact_text(raw_path: Optional[str], max_chars: int = 12000) -> Optional[str]:
    path = _resolve_local_artifact_path(raw_path)
    if not path:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[:max_chars]


def _task_context_for_prompt(
    ctx: Optional[Dict[str, Any]],
    bound_segment_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return task context safe for LLM prompts without stale segment calculations."""
    safe_ctx = dict(ctx or {})
    for key in SEGMENT_CONTEXT_STALE_KEYS:
        safe_ctx.pop(key, None)
    if bound_segment_info:
        for key in list(safe_ctx.keys()):
            if key.startswith("segment_") or key in {"selected_segment_locked"}:
                safe_ctx.pop(key, None)
        safe_ctx["selected_segment"] = {
            "id": bound_segment_info["id"],
            "name": bound_segment_info["name"],
            "customer_count": int(bound_segment_info["count"] or 0),
            "edit_path": bound_segment_info["edit_path"],
            "source": "live_db_recalculation",
        }
    return safe_ctx


async def _get_analytics_agent_context_text(db: AsyncSession, days: int = 7) -> str:
    """Build live data context for AI Analytics conversations and task execution."""
    try:
        data = await DirectorDataService(db).get_analytics_agent_data_context(days)
        return (
            "=== ЖИВОЙ DATA-КОНТЕКСТ AI ANALYTICS ===\n"
            "Источники: офлайн-посещения магазинов, посещаемость сайта, поведение Flutter-приложения, "
            "Instagram analytics и продажи/чеки.\n"
            f"{json.dumps(data, ensure_ascii=False, default=str)}"
        )
    except Exception as e:
        logger.warning("Failed to build analytics agent data context", exc_info=True)
        return (
            "=== ЖИВОЙ DATA-КОНТЕКСТ AI ANALYTICS ===\n"
            f"Не удалось получить часть live-данных: {e}. "
            "Сообщи пользователю, какой источник недоступен, и не придумывай значения."
        )


async def _get_assortment_agent_context_text(db: AsyncSession, source_text: str, days: int = 90) -> str:
    """Build live catalog/stock/sales context for AI Assortment conversations."""
    try:
        from app.models.product import Product
        from app.models.product_stock import ProductStock
        from app.models.store import Store
        from app.models.sales_record import SalesRecord
        from app.services.inventory_control_service import InventoryControlService

        src_l = (source_text or "").lower()

        stores_result = await db.execute(
            select(Store.external_id, Store.name, Store.city)
            .where(Store.is_active == True)
            .order_by(Store.name.asc())
        )
        stores = [
            {"external_id": str(ext or ""), "name": name or "", "city": city or ""}
            for ext, name, city in stores_result.all()
        ]
        selected_store = None
        for store in stores:
            name_l = store["name"].lower()
            city_l = store["city"].lower()
            if (
                ("центр" in src_l or "центрум" in src_l) and ("центр" in name_l or "центрум" in name_l)
            ) or (
                "ялт" in src_l and ("ялт" in name_l or "ялт" in city_l)
            ) or (
                "мрия" in src_l and ("мрия" in name_l or "мрия" in city_l)
            ) or (
                "симферопол" in src_l and ("симферопол" in city_l or "центр" in name_l or "центрум" in name_l)
            ):
                selected_store = store
                break

        brands_result = await db.execute(
            select(Product.brand)
            .where(Product.is_active == True, Product.brand.isnot(None), Product.brand != "")
            .distinct()
            .limit(500)
        )
        brands = [str(row[0]).strip() for row in brands_result.all() if row and str(row[0] or "").strip()]
        selected_brand = None
        for brand in sorted(brands, key=len, reverse=True):
            if brand.lower() in src_l:
                selected_brand = brand
                break
        if not selected_brand:
            for brand_hint in ("UNOde50", "Kalliope", "Claudio Canzian", "Raganella Princess", "Geometry", "Pearl", "Crystal", "Magna"):
                if brand_hint.lower() in src_l:
                    selected_brand = brand_hint
                    break

        product_conditions = [Product.is_active == True]
        if selected_brand:
            product_conditions.append(func.lower(Product.brand) == selected_brand.lower())

        total_products_result = await db.execute(select(func.count(Product.id)).where(and_(*product_conditions)))
        total_products = int(total_products_result.scalar() or 0)

        stock_conditions = []
        if selected_store and selected_store.get("external_id"):
            stock_conditions.append(ProductStock.store_id == selected_store["external_id"])

        stock_stmt = (
            select(
                func.count(func.distinct(Product.id)).label("sku_in_stock"),
                func.coalesce(func.sum(ProductStock.available_quantity), 0.0).label("stock_qty"),
            )
            .select_from(Product)
            .join(ProductStock, ProductStock.product_id == Product.id)
            .where(and_(*(product_conditions + stock_conditions)), ProductStock.available_quantity > 0)
        )
        stock_result = await db.execute(stock_stmt)
        sku_in_stock, stock_qty = stock_result.one()

        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        sales_conditions = [SalesRecord.sale_date >= cutoff]
        if selected_brand:
            sales_conditions.append(func.lower(SalesRecord.product_brand) == selected_brand.lower())
        if selected_store and selected_store.get("external_id"):
            sales_conditions.append(SalesRecord.store_id == selected_store["external_id"])
        sales_result = await db.execute(
            select(
                func.coalesce(func.sum(SalesRecord.revenue), 0.0).label("revenue"),
                func.coalesce(func.sum(SalesRecord.quantity), 0.0).label("qty"),
                func.count(func.distinct(func.coalesce(SalesRecord.document_id, SalesRecord.external_id))).label("checks"),
            ).where(and_(*sales_conditions))
        )
        revenue, qty, checks = sales_result.one()

        inventory = InventoryControlService(db)
        rows = await inventory.build_inventory_rows(
            analysis_period_days=max(1, days),
            store_id=None,
        )
        include_packaging = any(k in src_l for k in ["упаков", "пакет", "короб", "мешоч"])
        candidate_rows = [
            r for r in rows
            if r.stock_qty > 0 and (
                not selected_brand
                or (r.brand or "").lower() == selected_brand.lower()
            )
            and (
                include_packaging
                or not any(k in f"{r.category or ''} {r.nomenclature or ''}".lower() for k in ["упаков", "пакет", "короб", "мешоч", "сопутствующие материалы"])
            )
        ]

        selected_store_id = selected_store["external_id"] if selected_store else None
        candidate_ext_ids = [r.external_id for r in candidate_rows]
        stock_by_external_id: Dict[str, List[Dict[str, Any]]] = {}
        if candidate_ext_ids:
            stock_rows = await db.execute(
                select(
                    Product.external_id,
                    ProductStock.store_id,
                    Store.name,
                    Store.city,
                    ProductStock.quantity,
                    ProductStock.reserved_quantity,
                    ProductStock.available_quantity,
                    ProductStock.last_synced_at,
                )
                .select_from(ProductStock)
                .join(Product, ProductStock.product_id == Product.id)
                .outerjoin(Store, Store.external_id == ProductStock.store_id)
                .where(Product.external_id.in_(candidate_ext_ids))
                .order_by(Product.external_id.asc(), Store.name.asc().nulls_last(), ProductStock.store_id.asc())
            )
            for ext_id, store_id, store_name, city, quantity, reserved, available, synced_at in stock_rows.all():
                key = str(ext_id)
                stock_by_external_id.setdefault(key, []).append(
                    {
                        "store_id": store_id,
                        "store_name": store_name or store_id,
                        "city": city,
                        "quantity": float(quantity or 0.0),
                        "reserved_quantity": float(reserved or 0.0),
                        "available_quantity": float(available or 0.0),
                        "last_synced_at": synced_at.isoformat() if synced_at else None,
                    }
                )

        def _selected_store_qty(row: Any) -> float:
            if not selected_store_id:
                return 0.0
            return float(
                sum(
                    float(item.get("available_quantity") or 0.0)
                    for item in stock_by_external_id.get(row.external_id, [])
                    if item.get("store_id") == selected_store_id
                )
            )

        candidate_rows.sort(
            key=lambda r: (
                -_selected_store_qty(r),
                0 if r.sales_month > 0 else 1,
                -(r.sales_month or 0.0),
                -(r.stock_qty or 0.0),
                r.nomenclature,
            )
        )
        sample_rows = candidate_rows[:35]
        ext_ids = [r.external_id for r in sample_rows]
        product_meta: Dict[str, Dict[str, Any]] = {}
        if ext_ids:
            meta_result = await db.execute(
                select(
                    Product.external_id,
                    Product.id,
                    Product.article,
                    Product.barcode,
                    Product.name,
                    Product.brand,
                    Product.category,
                    Product.price,
                    Product.images,
                ).where(Product.external_id.in_(ext_ids))
            )
            for ext_id, pid, article, barcode, name, brand, category, price, images in meta_result.all():
                product_meta[str(ext_id)] = {
                    "id": str(pid),
                    "article": article,
                    "barcode": barcode,
                    "name": name,
                    "brand": brand,
                    "category": category,
                    "price": price,
                    "has_image": bool(images and isinstance(images, list) and len(images) > 0),
                }

        candidates = []
        for row in sample_rows:
            meta = product_meta.get(row.external_id) or {}
            stock_by_store = stock_by_external_id.get(row.external_id) or []
            selected_store_available = None
            if selected_store_id:
                selected_store_available = sum(
                    float(item.get("available_quantity") or 0.0)
                    for item in stock_by_store
                    if item.get("store_id") == selected_store_id
                )
            candidates.append(
                {
                    "product_id": meta.get("id"),
                    "external_id_1c": row.external_id,
                    "article": meta.get("article"),
                    "barcode": meta.get("barcode"),
                    "name": meta.get("name") or row.nomenclature,
                    "brand": meta.get("brand") or row.brand,
                    "category": meta.get("category") or row.category,
                    "price": meta.get("price"),
                    "stock_qty": row.stock_qty,
                    "selected_store_available_quantity": selected_store_available,
                    "stock_by_store": stock_by_store,
                    "sales_month": round(float(row.sales_month or 0.0), 2),
                    "stock_cover": round(float(row.stock_cover), 2) if row.stock_cover is not None else None,
                    "revenue_period": round(float(row.revenue or 0.0), 2),
                    "checks_period": row.checks_count,
                    "has_image": bool(meta.get("has_image")),
                }
            )

        sales_diagnostics_context: Dict[str, Any] = {"status": "not_loaded"}
        try:
            sales_diagnostics = await AssortmentMatrixAgent(db).sales_effectiveness_matrix(
                analysis_period_days=max(1, days),
                store_id=selected_store_id,
                brand=selected_brand,
                inventory_rows=candidate_rows,
                limit=35,
            )
            diagnostics = sales_diagnostics.get("diagnostics") or {}
            sales_diagnostics_context = {
                "status": "loaded",
                "period": sales_diagnostics.get("period"),
                "filters": sales_diagnostics.get("filters"),
                "summary": sales_diagnostics.get("summary"),
                "top_stores": (sales_diagnostics.get("stores") or [])[:8],
                "top_sellers": (sales_diagnostics.get("sellers") or [])[:12],
                "top_brands": (sales_diagnostics.get("brands") or [])[:8],
                "top_categories": (sales_diagnostics.get("categories") or [])[:8],
                "position_diagnostics": (sales_diagnostics.get("positions") or [])[:20],
                "stock_without_sales_count": len(diagnostics.get("stock_without_sales") or []),
                "low_or_no_stock_with_sales_count": len(diagnostics.get("low_or_no_stock_with_sales") or []),
                "seller_personal_conclusions": diagnostics.get("seller_personal_conclusions"),
                "data_quality": sales_diagnostics.get("data_quality"),
                "warnings": sales_diagnostics.get("warnings"),
            }
        except Exception as diagnostics_error:
            logger.warning("Failed to build assortment sales diagnostics context", exc_info=True)
            sales_diagnostics_context = {"status": "failed", "error": str(diagnostics_error)}

        api_tools = [
            "GET /api/products/paged?brand=UNOde50&in_stock=true&limit=100 — каталог платформы с ценами, артикулами, фото и остатком.",
            "GET /api/products?brand=UNOde50&variants_only=true — варианты товаров из синхронизированного каталога.",
            "GET /api/inventory/dashboard?period=month&store_id=<store_external_id> — продажи, чеки, общий складской срез.",
            "GET /api/inventory/assortment?period=month&store_id=<store_external_id>&seller_id=<seller_1c_key>&force_refresh=true — матрица ассортимента плюс seller/store sales диагностика без кэша.",
            "GET /api/inventory/marketing-link?period=month&store_id=<store_external_id>&limit=200 — связка маркетинг/остатки/оборачиваемость.",
            "GET /api/analytics/inventory/store-distribution — распределение остатков по магазинам.",
            "GET /api/content/products/search?query=<article_or_name> — поиск товара по артикулу/названию.",
        ]

        payload = {
            "source": "platform_db_synced_with_1c",
            "data_contract": {
                "catalog_table": "products",
                "stock_table": "product_stocks",
                "sales_table": "sales_records",
                "stores_table": "stores",
                "product_keys": ["products.id", "products.external_id (1C Номенклатура_Key)", "article", "barcode"],
                "stock_key": "product_stocks.store_id = stores.external_id",
                "sales_key": "sales_records.product_id = products.external_id",
            },
            "selected_filters_from_request": {
                "brand": selected_brand,
                "store": selected_store,
                "period_days": days,
            },
            "availability_summary": {
                "catalog_products": total_products,
                "sku_in_stock": int(sku_in_stock or 0),
                "stock_qty": float(stock_qty or 0.0),
                "sales_revenue_period": float(revenue or 0.0),
                "sales_qty_period": float(qty or 0.0),
                "checks_period": int(checks or 0),
            },
            "seller_store_sales_diagnostics": sales_diagnostics_context,
            "active_stores": stores,
            "candidate_products_from_db": candidates,
            "available_api_tools": api_tools,
        }
        return (
            "=== ЖИВОЙ DATA-КОНТЕКСТ AI ASSORTMENT ===\n"
            "У тебя есть доступ к синхронизированной БД платформы GLAME. Не проси Excel/CSV, "
            "если ниже есть данные. Используй только реальные SKU из candidate_products_from_db; "
            "если выборка мала или пуста, прямо напиши, каких данных нет и какой API/синхронизацию нужно запустить. "
            "Не выдумывай артикулы, цены, остатки или магазины.\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )
    except Exception as e:
        logger.warning("Failed to build assortment agent data context", exc_info=True)
        return (
            "=== ЖИВОЙ DATA-КОНТЕКСТ AI ASSORTMENT ===\n"
            f"Не удалось получить каталог/остатки/продажи из БД: {e}. "
            "Сообщи пользователю причину и предложи запустить синхронизацию каталога/остатков/продаж, не выдумывай SKU."
        )


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateAgentTaskRequest(BaseModel):
    source_agent: str = Field(..., min_length=1, max_length=64, description="Агент-инициатор")
    target_agent: str = Field(..., min_length=1, max_length=64, description="Целевой агент")
    task_type: str = Field(..., min_length=1, max_length=100, description="Тип задачи")
    task_context: Dict[str, Any] = Field(default_factory=dict, description="Контекст задачи")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Входные данные")
    target_metrics: Optional[Dict[str, Any]] = Field(None, description="Целевые метрики")
    requirements: Optional[Dict[str, Any]] = Field(None, description="Требования к результату")
    constraints: Optional[Dict[str, Any]] = Field(None, description="Ограничения")
    priority: int = Field(default=TaskPriority.NORMAL.value, ge=1, le=5, description="Приоритет (1-5, lower is higher)")
    deadline_at: Optional[datetime] = Field(None, description="Дедлайн выполнения")
    timeout_seconds: Optional[int] = Field(300, ge=10, description="Таймаут в секундах")


class UpdateAgentTaskRequest(BaseModel):
    task_type: Optional[str] = Field(None, min_length=1, max_length=100)
    task_context: Optional[Dict[str, Any]] = None
    input_data: Optional[Dict[str, Any]] = None
    target_metrics: Optional[Dict[str, Any]] = None
    requirements: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    deadline_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None


class AgentTaskResponse(BaseModel):
    id: str
    source_agent: str
    target_agent: str
    task_type: str
    task_context: Dict[str, Any] = Field(default_factory=dict)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    target_metrics: Dict[str, Any] = Field(default_factory=dict)
    requirements: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    status: str
    priority: int
    validation_result: Optional[Dict[str, Any]]
    validation_errors: List[str]
    output_data: Optional[Dict[str, Any]] = None
    output_metadata: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: str
    scheduled_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    deadline_at: Optional[str]

    class Config:
        from_attributes = True


class ValidationResultResponse(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    rules_checked: int
    timestamp: str


class TaskLogResponse(BaseModel):
    id: str
    task_id: str
    agent_name: str
    event_type: str
    message: Optional[str]
    event_data: Dict[str, Any]
    created_at: str


class InteractionChainResponse(BaseModel):
    task: Dict[str, Any]
    logs: List[Dict[str, Any]]
    content_handoffs: List[Dict[str, Any]]
    audit_summary: Dict[str, Any]


class CreateValidationRuleRequest(BaseModel):
    task_type: str = Field(..., description="Тип задачи для валидации")
    rule_name: str = Field(..., description="Название правила")
    rule_description: Optional[str] = Field(None, description="Описание правила")
    validation_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema для валидации")
    validation_function: Optional[str] = Field(None, description="Имя кастомной функции валидации")
    source_agent: Optional[str] = Field(None, description="Применять только для конкретного источника")
    target_agent: Optional[str] = Field(None, description="Применять только для конкретного получателя")
    is_required: bool = Field(True, description="Обязательное правило")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")
    priority: int = Field(100, ge=0, description="Приоритет применения")


class ValidationRuleResponse(BaseModel):
    id: str
    task_type: str
    rule_name: str
    rule_description: Optional[str]
    source_agent: Optional[str]
    target_agent: Optional[str]
    is_required: bool
    is_active: bool
    priority: int
    created_at: str


# ============================================================================
# Endpoints для управления задачами
# ============================================================================

@router.post("/tasks", response_model=AgentTaskResponse)
async def create_agent_task(
    request: CreateAgentTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Создание новой задачи для межагентного взаимодействия.
    Задача автоматически проходит валидацию перед постановкой в очередь.
    """
    service = AgentInteractionService(db)

    if request.task_type == "agent_control_chat":
        raise HTTPException(
            status_code=400,
            detail="agent_control_chat is a service chat channel and must not be created as a task",
        )

    execution_agent = _execution_agent_id(request.target_agent)

    # Создаем задачу через AdvancedContentAgent (если целевой агент - Brand/Personal Media)
    if execution_agent == "content-agent":
        agent = AdvancedContentAgent(db)
        task = await agent.receive_task_from_agent(
            source_agent=request.source_agent,
            task_type=request.task_type,
            task_context=request.task_context,
            input_data=request.input_data,
            target_metrics=request.target_metrics,
            requirements=request.requirements,
            constraints=request.constraints,
            priority=request.priority,
            deadline_at=request.deadline_at
        )
        if request.target_agent != execution_agent:
            task.target_agent = request.target_agent
            db.add(task)
            await db.commit()
            await db.refresh(task)
    else:
        # Другие агенты - прямое создание
        task = AgentInteractionTask(
            source_agent=request.source_agent,
            target_agent=request.target_agent,
            task_type=request.task_type,
            task_context=request.task_context,
            input_data=request.input_data,
            target_metrics=request.target_metrics or {},
            requirements=request.requirements or {},
            constraints=request.constraints or {},
            priority=request.priority,
            status=InteractionStatus.PENDING.value,
            deadline_at=request.deadline_at,
            timeout_seconds=request.timeout_seconds
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    # Запускаем валидацию
    await service.validate_incoming_task(task)

    return AgentTaskResponse(
        id=str(task.id),
        source_agent=task.source_agent,
        target_agent=task.target_agent,
        task_type=task.task_type,
        task_context=task.task_context or {},
        input_data=task.input_data or {},
        target_metrics=task.target_metrics or {},
        requirements=task.requirements or {},
        constraints=task.constraints or {},
        status=task.status,
        priority=task.priority,
        validation_result=task.validation_result,
        validation_errors=task.validation_errors or [],
        output_data=task.output_data,
        output_metadata=task.output_metadata or {},
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        scheduled_at=task.scheduled_at.isoformat() if task.scheduled_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        deadline_at=task.deadline_at.isoformat() if task.deadline_at else None
    )


@router.get("/tasks", response_model=List[AgentTaskResponse])
async def list_agent_tasks(
    target_agent: Optional[str] = Query(None, description="Фильтр по целевому агенту"),
    source_agent: Optional[str] = Query(None, description="Фильтр по исходному агенту"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка задач межагентного взаимодействия"""
    query = (
        select(AgentInteractionTask)
        .where(
            and_(
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
                AgentInteractionTask.task_type != "agent_control_chat",
            )
        )
        .order_by(desc(AgentInteractionTask.created_at))
        .limit(limit)
    )

    if target_agent:
        query = query.where(AgentInteractionTask.target_agent == target_agent)
    if source_agent:
        query = query.where(AgentInteractionTask.source_agent == source_agent)
    if status:
        query = query.where(AgentInteractionTask.status == status)
    if task_type:
        query = query.where(AgentInteractionTask.task_type == task_type)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [
        AgentTaskResponse(
            id=str(t.id),
            source_agent=t.source_agent,
            target_agent=t.target_agent,
            task_type=t.task_type,
            task_context=t.task_context or {},
            input_data=t.input_data or {},
            target_metrics=t.target_metrics or {},
            requirements=t.requirements or {},
            constraints=t.constraints or {},
            status=t.status,
            priority=t.priority,
            validation_result=t.validation_result,
            validation_errors=t.validation_errors or [],
            output_data=t.output_data,
            output_metadata=t.output_metadata or {},
            error_message=t.error_message,
            created_at=t.created_at.isoformat() if t.created_at else None,
            scheduled_at=t.scheduled_at.isoformat() if t.scheduled_at else None,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            deadline_at=t.deadline_at.isoformat() if t.deadline_at else None
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение деталей задачи по ID"""
    service = AgentInteractionService(db)
    task = await service.get_task_by_id(str(task_id))

    if not task or task.status == InteractionStatus.DELETED.value:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return AgentTaskResponse(
        id=str(task.id),
        source_agent=task.source_agent,
        target_agent=task.target_agent,
        task_type=task.task_type,
        task_context=task.task_context or {},
        input_data=task.input_data or {},
        target_metrics=task.target_metrics or {},
        requirements=task.requirements or {},
        constraints=task.constraints or {},
        status=task.status,
        priority=task.priority,
        validation_result=task.validation_result,
        validation_errors=task.validation_errors or [],
        output_data=task.output_data,
        output_metadata=task.output_metadata or {},
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        scheduled_at=task.scheduled_at.isoformat() if task.scheduled_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        deadline_at=task.deadline_at.isoformat() if task.deadline_at else None
    )


@router.patch("/tasks/{task_id}", response_model=AgentTaskResponse)
async def update_agent_task(
    task_id: UUID,
    request: UpdateAgentTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Обновление паспорта задачи: поля глобального task object из ТЗ."""
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task or task.status == InteractionStatus.DELETED.value:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    previous = task.to_dict()

    if request.task_type is not None:
        task.task_type = request.task_type
    if request.task_context is not None:
        task.task_context = request.task_context
    if request.input_data is not None:
        task.input_data = request.input_data
    if request.target_metrics is not None:
        task.target_metrics = request.target_metrics
    if request.requirements is not None:
        task.requirements = request.requirements
    if request.constraints is not None:
        task.constraints = request.constraints
    if request.priority is not None:
        task.priority = request.priority
    if request.deadline_at is not None:
        task.deadline_at = request.deadline_at
    if request.scheduled_at is not None:
        task.scheduled_at = request.scheduled_at
    if request.status is not None:
        allowed_statuses = {s.value for s in InteractionStatus}
        if request.status not in allowed_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(allowed_statuses))}")
        task.status = request.status

    task.updated_at = datetime.utcnow()
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name=str(getattr(current_user, "email", None) or getattr(current_user, "id", None) or "ui"),
            event_type="task_updated",
            event_data={
                "before_status": previous.get("status"),
                "after_status": task.status,
                "updated_fields": list(
                    (
                        request.model_dump(exclude_unset=True)
                        if hasattr(request, "model_dump")
                        else request.dict(exclude_unset=True)
                    ).keys()
                ),
            },
            message="Паспорт задачи обновлен",
        )
    )
    updated_fields = list(
        (
            request.model_dump(exclude_unset=True)
            if hasattr(request, "model_dump")
            else request.dict(exclude_unset=True)
        ).keys()
    )
    auto_result = None
    try:
        async with db.begin_nested():
            auto_result = await _auto_prepare_crm_segment_from_task_passport(
                db=db,
                task=task,
                actor_name=str(getattr(current_user, "email", None) or getattr(current_user, "id", None) or "ui"),
                updated_fields=updated_fields,
            )
    except Exception as exc:
        logger.warning("CRM passport auto-run failed for task %s", task_id, exc_info=True)
        db.add(
            AgentInteractionLog(
                task_id=task.id,
                agent_name="crm-passport-auto-run",
                event_type="error",
                event_data={"error": str(exc), "updated_fields": updated_fields},
                message="Не удалось автоматически запустить AI CRM по обновленному паспорту",
            )
        )
    if not auto_result and _should_start_dialog_from_passport_update(previous, task, updated_fields):
        try:
            await _append_passport_update_dialog_request(
                db=db,
                task=task,
                actor_name=str(getattr(current_user, "email", None) or getattr(current_user, "id", None) or "ui"),
                updated_fields=updated_fields,
            )
        except Exception:
            logger.warning("Failed to append passport update dialog request for task %s", task_id, exc_info=True)
    if auto_result:
        task.output_data = {
            **(task.output_data or {}),
            "segment_id": auto_result["segment_id"],
            "segment_name": auto_result["segment_name"],
            "segment_customer_count": auto_result["customer_count"],
            "segment_rules": auto_result["rules"],
            "agent_reply": auto_result["reply"],
            "needs_user_attention": True,
        }
        task.output_metadata = {
            **(task.output_metadata or {}),
            "closed_by": "crm-passport-auto-run",
            "closure_status": InteractionStatus.PENDING_APPROVAL.value,
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        task.status = InteractionStatus.PENDING_APPROVAL.value
    await db.commit()
    await db.refresh(task)

    return AgentTaskResponse(
        id=str(task.id),
        source_agent=task.source_agent,
        target_agent=task.target_agent,
        task_type=task.task_type,
        task_context=task.task_context or {},
        input_data=task.input_data or {},
        target_metrics=task.target_metrics or {},
        requirements=task.requirements or {},
        constraints=task.constraints or {},
        status=task.status,
        priority=task.priority,
        validation_result=task.validation_result,
        validation_errors=task.validation_errors or [],
        output_data=task.output_data,
        output_metadata=task.output_metadata or {},
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        scheduled_at=task.scheduled_at.isoformat() if task.scheduled_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        deadline_at=task.deadline_at.isoformat() if task.deadline_at else None
    )


@router.post("/tasks/{task_id}/validate", response_model=ValidationResultResponse)
async def validate_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Принудительная валидация задачи"""
    service = AgentInteractionService(db)

    task = await service.get_task_by_id(str(task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    result = await service.validate_incoming_task(task)

    return ValidationResultResponse(
        is_valid=result["is_valid"],
        errors=result["errors"],
        warnings=result["warnings"],
        rules_checked=result["rules_checked"],
        timestamp=result["timestamp"]
    )


@router.post("/tasks/{task_id}/queue")
async def queue_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Постановка валидированной задачи в очередь на выполнение"""
    service = AgentInteractionService(db)

    try:
        task = await service.queue_task(str(task_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Задача поставлена в очередь",
        "task_id": str(task.id),
        "priority": task.priority,
        "status": task.status
    }


@router.post("/tasks/{task_id}/process")
async def process_agent_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Обработка задачи целевым агентом"""
    task_result = await db.execute(
        select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
    )
    task = task_result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    try:
        agent_execution_dispatcher.require_process_status_allowed(task.status)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    execution_agent = _execution_agent_id(task.target_agent)

    hermes_task_service = HermesTaskExecutionService()
    if await hermes_task_service.execute(task, db):
        return {
            "message": "Задача обработана через Hermes runtime",
            "task_id": str(task_id),
            "runtime": "hermes",
            "status": task.status,
            "output_data": task.output_data,
            "output_metadata": task.output_metadata or {},
        }

    if execution_agent == "director-agent":
        try:
            await db.refresh(task)
            if task.status == InteractionStatus.COMPLETED.value and task.output_data:
                return {
                    "message": "Задача директора уже обработана",
                    "task_id": str(task_id),
                    "result_summary": {
                        "summary": (task.output_data or {}).get("summary"),
                        "artifact_md_found": bool((task.output_data or {}).get("artifact_md_excerpt")),
                    },
                }
            task.status = InteractionStatus.PROCESSING.value
            task.started_at = datetime.utcnow()
            db.add(task)
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="director-agent",
                    event_type="start",
                    event_data={"task_type": task.task_type},
                    message="started",
                )
            )
            await db.commit()
            await db.refresh(task)

            input_data = task.input_data or {}
            context = task.task_context or {}
            sources = input_data.get("sources") if isinstance(input_data.get("sources"), dict) else {}
            title = input_data.get("title") or context.get("title") or task.task_type.replace("_", " ")
            description = input_data.get("description") or ""
            expected_result = input_data.get("expected_result") or ""
            monitor_summary = input_data.get("monitor_summary") or ""
            artifact_md_path = context.get("artifact_md") or input_data.get("artifact_md")
            artifact_json_path = context.get("artifact_json") or input_data.get("artifact_json")
            artifact_md = _read_task_artifact_text(artifact_md_path)

            checked_sources: List[Dict[str, Any]] = []
            for name, payload in sources.items():
                if not isinstance(payload, dict):
                    continue
                checked_sources.append(
                    {
                        "name": name,
                        "endpoint": payload.get("endpoint"),
                        "http_status": payload.get("http_status"),
                        "status": payload.get("status"),
                        "last_sync": payload.get("last_sync"),
                        "latest_metric_date": payload.get("latest_metric_date"),
                        "latest_nonzero_date": payload.get("latest_nonzero_date"),
                        "detail": payload.get("detail"),
                    }
                )

            stale_customer_sync = (sources.get("admin_1c_sync_status") or {}).get("last_sync") if sources else None
            latest_sales_date = (sources.get("sales_daily") or {}).get("latest_nonzero_date") if sources else None
            product_sync_detail = (sources.get("products_sync_status") or {}).get("detail") if sources else None

            summary_parts = []
            if monitor_summary:
                summary_parts.append(str(monitor_summary))
            elif description:
                summary_parts.append(str(description))
            if stale_customer_sync:
                summary_parts.append(f"Последняя customer sync: {stale_customer_sync}.")
            if latest_sales_date:
                summary_parts.append(f"Последняя ненулевая дата продаж: {latest_sales_date}.")
            summary = " ".join(summary_parts).strip() or "Задача директора обработана и зафиксирована."

            report_lines = [
                f"**AI Marketing Director | {title}**",
                "",
                "**Статус:** задача одобрена администратором и обработана директором.",
            ]
            if description:
                report_lines.extend(["", "**Суть:**", str(description)])
            if monitor_summary:
                report_lines.extend(["", "**Краткий вывод мониторинга:**", str(monitor_summary)])
            if expected_result:
                report_lines.extend(["", "**Ожидаемое решение:**", str(expected_result)])
            if checked_sources:
                report_lines.extend(["", "**Проверенные источники:**"])
                for source in checked_sources[:12]:
                    details = []
                    if source.get("http_status") is not None:
                        details.append(f"HTTP {source['http_status']}")
                    if source.get("status"):
                        details.append(f"status={source['status']}")
                    if source.get("last_sync"):
                        details.append(f"last_sync={source['last_sync']}")
                    if source.get("latest_metric_date"):
                        details.append(f"latest_metric_date={source['latest_metric_date']}")
                    if source.get("latest_nonzero_date"):
                        details.append(f"latest_nonzero_date={source['latest_nonzero_date']}")
                    if source.get("detail"):
                        details.append(str(source["detail"])[:240])
                    suffix = f" — {'; '.join(details)}" if details else ""
                    endpoint = f" `{source['endpoint']}`" if source.get("endpoint") else ""
                    report_lines.append(f"- `{source['name']}`{endpoint}{suffix}")
            report_lines.extend(
                [
                    "",
                    "**Следующее действие:** проверить расписания и фактический запуск 1С customer sync, sales/checks sync и stock/inventory analytics recalculation. Массовые CRM-действия по этим данным не запускать до подтверждения свежести.",
                ]
            )
            if product_sync_detail:
                report_lines.extend(["", f"**Сигнал по товарам:** {product_sync_detail}"])
            if artifact_md:
                report_lines.extend(["", "**Артефакт отчета:** приложен к результату задачи."])

            report = "\n".join(report_lines)
            task.output_data = {
                "summary": summary,
                "report": report,
                "sources": checked_sources,
                "artifact_md_path": artifact_md_path,
                "artifact_json_path": artifact_json_path,
                "artifact_md_excerpt": artifact_md,
            }
            task.output_metadata = {
                **(task.output_metadata or {}),
                "processed_by": "director-agent",
                "processed_at": datetime.utcnow().isoformat(),
                "artifact_md_found": bool(artifact_md),
            }
            task.status = InteractionStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.add(task)
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="director-agent",
                    event_type="dialog_message",
                    event_data={"role": "assistant", "kind": "assistant_reply", "source": "task_process"},
                    message=report,
                )
            )
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="director-agent",
                    event_type="completed",
                    event_data={"result_keys": list((task.output_data or {}).keys())},
                    message="completed",
                )
            )
            await db.commit()
            return {
                "message": "Задача директора обработана",
                "task_id": str(task_id),
                "result_summary": {"summary": summary, "artifact_md_found": bool(artifact_md)},
            }
        except Exception as e:
            await db.rollback()
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="director-agent",
                    event_type="failed",
                    event_data={"error": str(e)},
                    message="failed",
                )
            )
            task.status = InteractionStatus.FAILED.value
            task.error_message = str(e)
            db.add(task)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

    if execution_agent == "content-agent":
        agent = AdvancedContentAgent(db)
        try:
            result = await agent.process_agent_task(str(task_id))
            return {
                "message": "Задача успешно обработана",
                "task_id": str(task_id),
                "result_summary": {k: v for k, v in result.items() if k != "raw_response"} if isinstance(result, dict) else {}
            }
        except Exception as e:
            logger.error(f"Ошибка обработки задачи {task_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    if execution_agent == "communication-agent":
        try:
            await db.refresh(task)
            task.status = InteractionStatus.PROCESSING.value
            task.started_at = datetime.utcnow()
            db.add(task)
            db.add(AgentInteractionLog(task_id=task.id, agent_name="communication-agent", event_type="start", event_data={"task_type": task.task_type}, message="started"))
            await db.commit()
            await db.refresh(task)
            service = CommunicationService(db)
            agent = CommunicationAgent(db)
            input_data = task.input_data or {}
            event = input_data.get("event") or {}
            limit = int(input_data.get("limit") or 1000)
            search_criteria = input_data.get("search_criteria")
            client_ids: List[UUID] = []
            raw_client_ids = input_data.get("client_ids")
            if isinstance(raw_client_ids, list) and raw_client_ids:
                ids: List[UUID] = []
                for cid in raw_client_ids:
                    try:
                        ids.append(UUID(str(cid)))
                    except Exception:
                        pass
                client_ids = ids
            if not client_ids:
                et = str(event.get("type") or "")
                client_ids = await service.find_clients_for_event(et, event, limit=limit, search_criteria=search_criteria)
            rows: List[Dict[str, Any]] = []
            for cid in client_ids:
                try:
                    msg = await agent.generate_message(cid, event)
                    payload = dict(msg)
                    payload["task_id"] = str(task.id)
                    payload["message_kind"] = "task"
                    rows.append(
                        {
                            "id": uuid.uuid4(),
                            "user_id": cid,
                            "message": payload.get("message") or "",
                            "cta": payload.get("cta"),
                            "segment": payload.get("segment"),
                            "event_type": event.get("type"),
                            "event_brand": event.get("brand"),
                            "event_store": event.get("store"),
                            "payload": payload,
                            "status": "new",
                        }
                    )
                except Exception as e:
                    db.add(AgentInteractionLog(task_id=task.id, agent_name="communication-agent", event_type="error", event_data={"client_id": str(cid)}, message=str(e)))
            rows = [r for r in rows if r.get("message")]
            if rows:
                await db.execute(CustomerMessage.__table__.insert().values(rows))
            task.status = InteractionStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.add(task)
            db.add(AgentInteractionLog(task_id=task.id, agent_name="communication-agent", event_type="completed", event_data={"recipients": len(client_ids), "saved": len(rows)}, message="completed"))
            await db.commit()
            return {"message": "Задача выполнена", "task_id": str(task_id), "recipients": len(client_ids), "saved": len(rows)}
        except Exception as e:
            await db.rollback()
            db.add(AgentInteractionLog(task_id=task.id, agent_name="communication-agent", event_type="failed", event_data={"error": str(e)}, message="failed"))
            task.status = InteractionStatus.FAILED.value
            db.add(task)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    if task.target_agent == "analytics-agent":
        try:
            await db.refresh(task)
            task.status = InteractionStatus.PROCESSING.value
            task.started_at = datetime.utcnow()
            db.add(task)
            db.add(AgentInteractionLog(task_id=task.id, agent_name="analytics-agent", event_type="start", event_data={"task_type": task.task_type}, message="started"))
            await db.commit()
            agent = MarketingAgent(db)
            input_data = task.input_data or {}
            campaign_id = input_data.get("campaign_id")
            channel = input_data.get("channel")
            start_date = input_data.get("start_date")
            end_date = input_data.get("end_date")
            result: Dict[str, Any] = {}
            if campaign_id:
                try:
                    from datetime import datetime as _dt
                    sd = _dt.fromisoformat(start_date) if isinstance(start_date, str) else None
                    ed = _dt.fromisoformat(end_date) if isinstance(end_date, str) else None
                except Exception:
                    sd = None
                    ed = None
                result = await agent.analyze_campaign_performance(campaign_id=campaign_id, channel=channel, start_date=sd, end_date=ed)
            else:
                live_context = await _get_analytics_agent_context_text(db, 30)
                prompt = (
                    "Проанализируй ключевые маркетинговые метрики за последние 30 дней и предложи 3 действия.\n\n"
                    f"{live_context}"
                )
                system = await agent.get_active_system_prompt(db, "analytics-agent", agent.BRAND_SYSTEM_PROMPT)
                text = await agent.generate_response(prompt=prompt, system_prompt=system, temperature=0.3, max_tokens=800)
                result = {"summary": text}
            task.status = InteractionStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.add(task)
            db.add(AgentInteractionLog(task_id=task.id, agent_name="analytics-agent", event_type="completed", event_data=result, message="completed"))
            await db.commit()
            return {"message": "Задача выполнена", "task_id": str(task_id), "result": result}
        except Exception as e:
            await db.rollback()
            db.add(AgentInteractionLog(task_id=task.id, agent_name="analytics-agent", event_type="failed", event_data={"error": str(e)}, message="failed"))
            task.status = InteractionStatus.FAILED.value
            db.add(task)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    if execution_agent in (
        "inventory-procurement-agent",
        "inventory-control-agent",
        "clearance-agent",
        "assortment-matrix-agent",
        "merchandising-agent",
        "pricing-agent",
        "marketing-inventory-agent",
    ):
        agent_name = execution_agent
        try:
            await db.refresh(task)
            task.status = InteractionStatus.PROCESSING.value
            task.started_at = datetime.utcnow()
            db.add(task)
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name=agent_name,
                    event_type="start",
                    event_data={"task_type": task.task_type},
                    message="started",
                )
            )
            await db.commit()
            await db.refresh(task)

            input_data = task.input_data or {}
            analysis_period_days = int(input_data.get("analysis_period_days") or 90)
            period = (input_data.get("period") or "").strip().lower() or None
            start_date_raw = input_data.get("start_date")
            end_date_raw = input_data.get("end_date")

            def _parse_date(v) -> Optional[date]:
                if v is None:
                    return None
                s = str(v).strip()
                if not s:
                    return None
                return date.fromisoformat(s)

            def _resolve_period() -> tuple[datetime, datetime, int]:
                today = datetime.now(timezone.utc).date()
                if period in {"week", "month", "quarter", "year"}:
                    days = {"week": 7, "month": 30, "quarter": 90, "year": 365}[period]
                    end_d = today
                    start_d = end_d - timedelta(days=days - 1)
                elif period == "custom":
                    sd = _parse_date(start_date_raw)
                    ed = _parse_date(end_date_raw)
                    if not sd or not ed:
                        raise ValueError("start_date and end_date are required for custom period")
                    if ed < sd:
                        sd, ed = ed, sd
                    start_d, end_d = sd, ed
                    days = (end_d - start_d).days + 1
                else:
                    days = max(1, int(analysis_period_days or 1))
                    end_d = today
                    start_d = end_d - timedelta(days=days - 1)

                start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
                end_dt = datetime.combine(end_d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
                return start_dt, end_dt, days

            try:
                start_dt, end_dt, resolved_days = _resolve_period()
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            store_id = input_data.get("store_id")
            seller_id = input_data.get("seller_id") or input_data.get("seller_external_id")
            seller_name = input_data.get("seller_name")
            category = input_data.get("category")
            color = input_data.get("color")
            brand = input_data.get("brand")
            collection = input_data.get("collection")
            limit = int(input_data.get("limit") or 5000)

            result: Dict[str, Any] = {}

            if agent_name == "inventory-procurement-agent":
                agent = InventoryProcurementAgent(db)
                annotate_limit = int(input_data.get("annotate_limit") or 30)
                result = await agent.build_reorder_table(
                    analysis_period_days=resolved_days,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    store_id=store_id,
                    category=category,
                    color=color,
                    brand=brand,
                    collection=collection,
                    annotate_limit=annotate_limit,
                )
            elif agent_name == "inventory-control-agent":
                agent = InventoryControlAgent(db)
                kind = str(input_data.get("kind") or task.task_type or "").lower()
                if "order" in kind or "reorder" in kind:
                    result = await agent.build_reorder_recommendations(
                        analysis_period_days=resolved_days,
                        start_dt=start_dt,
                        end_dt=end_dt,
                        store_id=store_id,
                        category=category,
                        color=color,
                        brand=brand,
                        collection=collection,
                        limit=limit,
                    )
                else:
                    result = await agent.build_report(
                        analysis_period_days=resolved_days,
                        start_dt=start_dt,
                        end_dt=end_dt,
                        store_id=store_id,
                        category=category,
                        color=color,
                        brand=brand,
                        collection=collection,
                        limit=limit,
                    )
            elif agent_name == "clearance-agent":
                agent = ClearanceAgent(db)
                result = await agent.build_clearance(
                    analysis_period_days=resolved_days, start_dt=start_dt, end_dt=end_dt, store_id=store_id, limit=limit
                )
            elif agent_name in {"assortment-matrix-agent", "marketing-inventory-agent"}:
                agent = AssortmentMatrixAgent(db)
                result = await agent.build_assortment(
                    analysis_period_days=resolved_days,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    store_id=store_id,
                    seller_id=seller_id,
                    seller_name=seller_name,
                    brand=brand,
                    category=category,
                    limit=limit,
                )
            elif agent_name == "merchandising-agent":
                agent = MerchandisingAgent(db)
                result = await agent.build_merchandising(
                    analysis_period_days=resolved_days, start_dt=start_dt, end_dt=end_dt, store_id=store_id, limit=limit
                )
            elif agent_name == "pricing-agent":
                agent = PricingAgent(db)
                result = await agent.build_pricing_report(
                    analysis_period_days=resolved_days, start_dt=start_dt, end_dt=end_dt, store_id=store_id, limit=limit
                )
            task.status = InteractionStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            db.add(task)
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name=agent_name,
                    event_type="completed",
                    event_data={"result_keys": list(result.keys())},
                    message="completed",
                )
            )
            await db.commit()
            return {"message": "Задача выполнена", "task_id": str(task_id), "result": result}
        except Exception as e:
            await db.rollback()
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name=agent_name,
                    event_type="failed",
                    event_data={"error": str(e)},
                    message="failed",
                )
            )
            task.status = InteractionStatus.FAILED.value
            db.add(task)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Обработка для агента '{task.target_agent}' не реализована")


@router.post("/tasks/{task_id}/cancel")
async def cancel_agent_task(
    task_id: UUID,
    reason: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Отмена задачи"""
    service = AgentInteractionService(db)

    try:
        task = await service.cancel_task(str(task_id), reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Задача отменена",
        "task_id": str(task.id),
        "status": task.status,
        "reason": reason
    }


@router.delete("/tasks/{task_id}")
async def delete_agent_task(
    task_id: UUID,
    reason: Optional[str] = Query(None, description="Причина удаления"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Мягкое удаление задачи с каскадным приведением связанных сущностей в консистентное состояние"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    if str(getattr(current_user, "role", "") or "") not in ("admin", "ai_marketer", "content_manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления задачи")

    service = AgentInteractionService(db)
    try:
        task = await service.delete_task(str(task_id), deleted_by=str(current_user.id) if getattr(current_user, "id", None) else None, reason=reason)
    except ValueError:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {"message": "Задача удалена", "task_id": str(task.id), "status": task.status}


class ApprovalRequest(BaseModel):
    comment: Optional[str] = None


@router.post("/tasks/{task_id}/approve")
async def approve_agent_task(
    task_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Одобрение задачи (аппрув) - реализация системы согласования из Enterprise Blueprint"""
    # Проверка прав: только пользователи с ролью, имеющей право одобрять задачи
    allowed_roles = ("admin", "ai_marketer", "content_manager", "store_manager")
    if str(getattr(current_user, "role", "") or "") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав для одобрения задачи")

    # Получаем задачу
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Проверяем, что задача находится в правильном статусе для одобрения.
    # validated/pending оставлены для старых задач и быстрых low-risk сценариев.
    allowed_statuses = {
        InteractionStatus.PENDING_APPROVAL.value,
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING.value,
    }
    if task.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Задача не ожидает одобрения")

    # Обновляем статус
    task.status = InteractionStatus.APPROVED.value
    task.updated_at = datetime.utcnow()
    task.input_data = {
        **(task.input_data or {}),
        "approval_status": "approved",
        "approval_comment": request.comment,
        "approved_at": datetime.utcnow().isoformat(),
    }

    # Логируем одобрение
    db.add(AgentInteractionLog(
        task_id=task.id,
        agent_name=str(current_user.email or current_user.id),
        event_type="task_approved",
        event_data={"approver_role": current_user.role, "comment": request.comment},
        message=f"Задача одобрена пользователем {current_user.email}"
    ))

    # После одобрения ставим задачу в очередь на выполнение
    task.status = InteractionStatus.QUEUED.value

    await db.commit()
    await db.refresh(task)

    return {
        "message": "Задача успешно одобрена и поставлена в очередь на выполнение",
        "task_id": str(task.id),
        "new_status": task.status
    }


@router.post("/tasks/{task_id}/reject")
async def reject_agent_task(
    task_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Отклонение задачи (репрув) - реализация системы согласования из Enterprise Blueprint"""
    # Проверка прав
    allowed_roles = ("admin", "ai_marketer", "content_manager", "store_manager")
    if str(getattr(current_user, "role", "") or "") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав для отклонения задачи")

    # Получаем задачу
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    allowed_statuses = {
        InteractionStatus.PENDING_APPROVAL.value,
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING.value,
        InteractionStatus.APPROVED.value,
        InteractionStatus.QUEUED.value,
    }
    if task.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Задача не ожидает одобрения")

    # Обновляем статус
    task.status = InteractionStatus.REJECTED.value
    task.updated_at = datetime.utcnow()
    task.input_data = {
        **(task.input_data or {}),
        "approval_status": "rejected",
        "approval_comment": request.comment,
        "rejected_at": datetime.utcnow().isoformat(),
    }

    # Логируем отклонение
    db.add(AgentInteractionLog(
        task_id=task.id,
        agent_name=str(current_user.email or current_user.id),
        event_type="task_rejected",
        event_data={"rejector_role": current_user.role, "comment": request.comment},
        message=f"Задача отклонена пользователем {current_user.email}: {request.comment}"
    ))

    await db.commit()
    await db.refresh(task)

    return {
        "message": "Задача отклонена",
        "task_id": str(task.id),
        "new_status": task.status,
        "rejection_comment": request.comment
    }


@router.post("/tasks/{task_id}/revise")
async def revise_agent_task(
    task_id: UUID,
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Запросить доработку задачи из approval queue."""
    allowed_roles = ("admin", "ai_marketer", "content_manager", "store_manager")
    if str(getattr(current_user, "role", "") or "") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав для отправки на доработку")

    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    allowed_statuses = {
        InteractionStatus.PENDING_APPROVAL.value,
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING.value,
        InteractionStatus.APPROVED.value,
        InteractionStatus.QUEUED.value,
    }
    if task.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Задачу нельзя отправить на доработку в текущем статусе")

    task.status = InteractionStatus.PENDING.value
    task.updated_at = datetime.utcnow()
    task.input_data = {
        **(task.input_data or {}),
        "approval_status": "needs_revision",
        "approval_comment": request.comment,
        "revision_requested_at": datetime.utcnow().isoformat(),
    }
    task.task_context = {
        **(task.task_context or {}),
        "revision_requested": True,
    }

    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name=str(current_user.email or current_user.id),
            event_type="task_revision_requested",
            event_data={"requester_role": current_user.role, "comment": request.comment},
            message=f"Задача отправлена на доработку пользователем {current_user.email}: {request.comment}",
        )
    )

    await db.commit()
    await db.refresh(task)

    return {
        "message": "Задача отправлена на доработку",
        "task_id": str(task.id),
        "new_status": task.status,
        "revision_comment": request.comment,
    }


# ============================================================================
# Endpoints для приоритизации
# ============================================================================

@router.get("/tasks/prioritized/{target_agent}", response_model=List[AgentTaskResponse])
async def get_prioritized_tasks(
    target_agent: str,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение приоритизированного списка задач для агента"""
    service = AgentInteractionService(db)

    tasks = await service.get_prioritized_tasks(
        target_agent=target_agent,
        status=status,
        limit=limit
    )

    return [
        AgentTaskResponse(
            id=str(t.id),
            source_agent=t.source_agent,
            target_agent=t.target_agent,
            task_type=t.task_type,
            task_context=t.task_context or {},
            input_data=t.input_data or {},
            target_metrics=t.target_metrics or {},
            requirements=t.requirements or {},
            constraints=t.constraints or {},
            status=t.status,
            priority=t.priority,
            validation_result=t.validation_result,
            validation_errors=t.validation_errors or [],
            output_data=t.output_data,
            output_metadata=t.output_metadata or {},
            error_message=t.error_message,
            created_at=t.created_at.isoformat() if t.created_at else None,
            scheduled_at=t.scheduled_at.isoformat() if t.scheduled_at else None,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            deadline_at=t.deadline_at.isoformat() if t.deadline_at else None
        )
        for t in tasks
    ]


# ============================================================================
# Endpoints для логирования и аудита
# ============================================================================

@router.get("/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение логов задачи"""
    service = AgentInteractionService(db)

    logs = await service.get_task_logs(str(task_id), limit)

    return [
        TaskLogResponse(
            id=str(l.id),
            task_id=str(l.task_id),
            agent_name=l.agent_name,
            event_type=l.event_type,
            message=l.message,
            event_data=l.event_data or {},
            created_at=l.created_at.isoformat() if l.created_at else None
        )
        for l in logs
    ]

class DialogLogRequest(BaseModel):
    role: str
    message: str
    metadata: Optional[Dict[str, Any]] = None


class StepType(str, Enum):
    PLANNING = "planning"
    SEGMENTATION = "segmentation"
    CONTENT = "content"
    ANALYTICS = "analytics"
    DISTRIBUTION = "distribution"
    OTHER = "other"


class ChatMetadata(BaseModel):
    step_type: Optional[StepType] = Field(None, description="Тип шага диалога, влияет на RAG/промпт")
    task_type: Optional[str] = Field(None, description="Тип задачи")
    dialog_model: Optional[str] = Field(None, description="Идентификатор модели для диалога")
    analytics_model: Optional[str] = Field(None, description="Идентификатор модели для аналитики")
    attachments: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Краткая сводка вложений")
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Произвольные доп. поля")


class ChatWithAgentRequest(BaseModel):
    message: str
    model: Optional[str] = Field(None, description="Модель LLM для диалога")
    metadata: Optional[ChatMetadata] = None


class ChatWithAgentResponse(BaseModel):
    reply: str
    used_brand_context: List[Dict[str, Any]] = []
    used_history_fragments: List[Dict[str, Any]] = []
    user_log_id: Optional[str] = None
    assistant_log_id: Optional[str] = None


class ChatHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: Optional[str] = None


@router.get("/tasks/{task_id}/chat", response_model=List[ChatHistoryItem])
async def get_task_chat_history(
    task_id: UUID,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    # Кэшируем необходимые значения до коммитов, чтобы избежать lazy-load после expire_on_commit
    task_id_str = str(task_id)
    task_agent_name = task.target_agent or "ai-marketer"

    result = await db.execute(
        select(AgentInteractionLog)
        .where(
            and_(
                AgentInteractionLog.task_id == task.id,
                AgentInteractionLog.event_type == "chat_reset",
            )
        )
        .order_by(desc(AgentInteractionLog.created_at))
        .limit(1)
    )
    reset_log = result.scalar_one_or_none()

    conditions = [
        AgentInteractionLog.task_id == task.id,
        AgentInteractionLog.event_type == "dialog_message",
    ]
    if reset_log and reset_log.created_at:
        conditions.append(AgentInteractionLog.created_at >= reset_log.created_at)

    result = await db.execute(
        select(AgentInteractionLog)
        .where(
            and_(*conditions)
        )
        .order_by(asc(AgentInteractionLog.created_at))
        .limit(limit)
    )
    logs = result.scalars().all()

    items: List[ChatHistoryItem] = []
    for l in logs:
        event_data = l.event_data or {}
        role = event_data.get("role")
        if role not in ("user", "assistant"):
            role = "assistant" if event_data.get("kind") == "assistant_reply" else "user"
        items.append(
            ChatHistoryItem(
                id=str(l.id),
                role=role,
                content=l.message or "",
                created_at=l.created_at.isoformat() if l.created_at else None,
            )
        )
    return items


@router.post("/tasks/{task_id}/dialog-logs")
async def append_task_dialog_log(
    task_id: UUID,
    body: DialogLogRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    log = AgentInteractionLog(
        task_id=task.id,
        agent_name=body.role or "user",
        event_type="dialog_message",
        event_data=body.metadata or {},
        message=body.message,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    try:
        text = f"[{body.role}] {body.message}"
        metadata = {
            "task_id": str(task_id),
            "role": body.role,
            "log_id": str(log.id),
            "created_at": log.created_at.isoformat() if log.created_at else None,
            **(body.metadata or {}),
        }
        vector_service.add_text_document(
            collection_name="task_dialogs",
            text=text,
            metadata=metadata,
        )
    except Exception:
        logger = logging.getLogger(__name__)
        logger.warning("Failed to index dialog log into vector DB", exc_info=True)
    return {"status": "ok", "log_id": str(log.id), "created_at": log.created_at.isoformat() if log.created_at else None}


@router.post("/tasks/{task_id}/chat", response_model=ChatWithAgentResponse)
async def chat_with_agent(
    task_id: UUID,
    body: ChatWithAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Диалог с AI-агентом по задаче.
    - сохраняет сообщение пользователя в лог и в RAG-коллекцию task_dialogs
    - подмешивает бренд-контекст и историю задачи
    - генерирует ответ через LLM и также логирует его
    """
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Cache fields that may be accessed after commits to avoid lazy-load in non-greenlet context
    task_id_str = str(task_id)
    task_agent_name = task.target_agent or "ai-marketer"

    # 1. Логируем и индексируем сообщение пользователя
    user_log = AgentInteractionLog(
        task_id=task.id,
        agent_name=(current_user.email if isinstance(current_user, User) and current_user.email else "user"),
        event_type="dialog_message",
        event_data=(body.metadata.dict(exclude_none=True) if isinstance(body.metadata, ChatMetadata) else (body.metadata or {})),
        message=body.message,
    )
    db.add(user_log)
    await db.commit()
    await db.refresh(user_log)
    user_log_id_str = str(user_log.id)

    try:
        vector_service.add_text_document(
            collection_name="task_dialogs",
            text=f"[user] {body.message}",
            metadata={
                "task_id": task_id_str,
                "role": "user",
                "log_id": user_log_id_str,
                "created_at": user_log.created_at.isoformat() if user_log.created_at else None,
                **(body.metadata.dict(exclude_none=True) if isinstance(body.metadata, ChatMetadata) else (body.metadata or {})),
            },
        )
    except Exception:
        logger = logging.getLogger(__name__)
        logger.warning("Failed to index user dialog message into vector DB", exc_info=True)

    # 2. Получаем бренд-контекст и фрагменты истории
    brand_context = []
    history_fragments = []
    try:
        brand_context = vector_service.get_brand_context(body.message, limit=3, score_threshold=0.4)
    except Exception:
        brand_context = []

    try:
        # Используем task_dialogs как RAG по истории задачи
        if vector_service.openai_client:
            history_fragments = vector_service.get_context(
                "task_dialogs",
                f"{body.message} task_id={task_id}",
                limit=5,
                score_threshold=0.2,
            )
            history_fragments = [
                item for item in history_fragments
                if str((item.get("payload") or {}).get("task_id") or "") == task_id_str
            ]
    except Exception:
        history_fragments = []

    # 2a. Если это ответ на конкретное сообщение — извлечь его и добавить как целевой контекст
    reply_to_text = ""
    try:
        reply_to_id = None
        if isinstance(body.metadata, ChatMetadata):
            reply_to_id = (body.metadata.extra or {}).get("reply_to_log_id")
        else:
            reply_to_id = (body.metadata or {}).get("extra", {}).get("reply_to_log_id")
        if reply_to_id:
            res = await db.execute(
                select(AgentInteractionLog).where(
                    and_(
                        AgentInteractionLog.id == UUID(str(reply_to_id)),
                        AgentInteractionLog.task_id == task.id,
                        AgentInteractionLog.event_type == "dialog_message",
                    )
                )
            )
            ref_log = res.scalar_one_or_none()
            if ref_log and (ref_log.message or "").strip():
                ref_role = (ref_log.event_data or {}).get("role") or ("assistant" if (ref_log.event_data or {}).get("kind") == "assistant_reply" else "user")
                reply_to_text = f"[{ref_role}] {ref_log.message}"
    except Exception:
        reply_to_text = ""

    def _format_ctx(items: List[Dict[str, Any]], header: str) -> str:
        if not items:
            return ""
        parts: List[str] = []
        for i, ctx in enumerate(items, 1):
            payload = ctx.get("payload") or {}
            text = payload.get("text") or ""
            source = payload.get("source") or payload.get("category") or ""
            score = ctx.get("score")
            meta_line = []
            if source:
                meta_line.append(f"источник: {source}")
            if score is not None:
                meta_line.append(f"релевантность: {score:.2f}")
            meta = f" ({', '.join(meta_line)})" if meta_line else ""
            parts.append(f"[{header} {i}{meta}]\n{text}")
        return "\n\n".join(parts)

    brand_ctx_text = _format_ctx(brand_context, "Бренд-контекст")
    history_ctx_text = _format_ctx(history_fragments, "История задачи")

    # 3. Строим промпт для LLM
    task_title = (task.input_data or {}).get("title") or task.task_type or ""
    # Определяем, является ли это первым ответом ассистента по задаче
    try:
        pre_assistant_exists = await db.execute(
            select(AgentInteractionLog.id)
            .where(
                and_(
                    AgentInteractionLog.task_id == task.id,
                    AgentInteractionLog.event_type == "dialog_message",
                    AgentInteractionLog.agent_name == task_agent_name,
                )
            )
            .limit(1)
        )
        is_first_assistant_reply = pre_assistant_exists.first() is None
    except Exception:
        is_first_assistant_reply = False
    prompt_agent_type = _prompt_agent_id(task_agent_name)
    active_prompt_text = None
    try:
        prompt_result = await db.execute(
            select(AgentSystemPrompt)
            .where(
                and_(
                    AgentSystemPrompt.agent_type == prompt_agent_type,
                    AgentSystemPrompt.is_active == True,
                )
            )
            .order_by(desc(AgentSystemPrompt.version))
            .limit(1)
        )
        active_prompt = prompt_result.scalar_one_or_none()
        if active_prompt and (active_prompt.system_prompt or "").strip():
            active_prompt_text = active_prompt.system_prompt.strip()
    except Exception:
        logger.warning("Failed to load active system prompt for %s", prompt_agent_type, exc_info=True)

    system_prompt = active_prompt_text or (
        "Ты — AI-агент бренда GLAME. "
        "Помогаешь планировать и выполнять операционные маркетинговые задачи. "
        "Учитывай бренд-контекст, историю задачи и отвечай конкретно, с шагами действий."
    )
    system_prompt = (
        f"{system_prompt}\n\n"
        "ЖЕСТКОЕ ПРАВИЛО ДОСТОВЕРНОСТИ GLAME: не придумывай цифры, товары, сегменты, остатки, продажи, "
        "клиентов, SKU, магазины, рекомендации и факты. Используй только данные, которые получены из БД/API "
        "платформы или явно переданы в контексте. Если нужных данных нет, они пустые, устарели или запрос к ним "
        "не удался, прямо напиши: каких данных нет, из какой таблицы/API они ожидались и какую синхронизацию "
        "или проверку нужно запустить. Нельзя заменять отсутствующие данные гипотезами."
    )
    metadata_extra = {}
    if isinstance(body.metadata, ChatMetadata):
        metadata_extra = body.metadata.extra or {}
    elif isinstance(body.metadata, dict):
        metadata_extra = (body.metadata.get("extra") or {}) if isinstance(body.metadata.get("extra"), dict) else {}
    is_identity_question = _is_agent_identity_question(body.message)
    selected_segment_id = metadata_extra.get("selected_segment_id") or metadata_extra.get("segment_id")
    try:
        seg_bound = bool(selected_segment_id or (task.task_context or {}).get("segment_id"))
    except Exception:
        seg_bound = False
    if is_identity_question and not selected_segment_id:
        seg_bound = False
    bound_segment_info = await _refresh_bound_segment_context(db, task, selected_segment_id) if seg_bound else None
    if bound_segment_info:
        seg_bound = True
    else:
        seg_bound = False

    context_blocks: List[str] = []
    if brand_ctx_text:
        context_blocks.append(f"=== КОНТЕКСТ БРЕНДА ===\n{brand_ctx_text}")
    if history_ctx_text and not (bound_segment_info and prompt_agent_type == "crm-agent"):
        context_blocks.append(f"=== ИСТОРИЯ ЗАДАЧИ ===\n{history_ctx_text}")
    if prompt_agent_type == "analytics-agent":
        context_blocks.append(await _get_analytics_agent_context_text(db, 14))
    if prompt_agent_type == "assortment-agent":
        context_blocks.append(await _get_assortment_agent_context_text(db, f"{task_title}\n{body.message}", 90))

    context_text = "\n\n".join(context_blocks).strip()
    is_director_handoff = bool(metadata_extra.get("from_director") or task.source_agent == "director-agent")

    prompt_parts: List[str] = []
    if task_title:
        prompt_parts.append(f"Задача: {task_title}")
    prompt_parts.append(f"Тип задачи: {task.task_type or 'не указан'}")
    # Учитываем уточнение шага из метаданных
    if isinstance(body.metadata, ChatMetadata) and body.metadata.step_type:
        prompt_parts.append(f"Текущий шаг: {body.metadata.step_type.value}")
    prompt_task_context = _task_context_for_prompt(task.task_context, bound_segment_info)
    if prompt_task_context:
        prompt_parts.append(f"Контекст задачи: {prompt_task_context}")
    if task.input_data:
        prompt_parts.append(f"Входные параметры задачи: {task.input_data}")
    if reply_to_text:
        prompt_parts.append(f"Сообщение, на которое требуется ответ/уточнение:\n{reply_to_text}")
    if bound_segment_info:
        prompt_parts.append(
            "=== ВЫБРАННЫЙ СЕГМЕНТ CRM ===\n"
            f"segment_id: {bound_segment_info['id']}\n"
            f"Название: {bound_segment_info['name']}\n"
            f"Фактический размер по правилам БД: {bound_segment_info['count']} покупателей\n"
            f"Путь редактирования: {bound_segment_info['edit_path']}\n"
            "ЖЕСТКОЕ ПРАВИЛО: в этом диалоге AI CRM анализирует и использует только этот выбранный сегмент. "
            "Не создавай, не переименовывай, не расширяй и не подменяй его другим сегментом. "
            "Во всех ответах и отчетах указывай именно этот segment_id, это название и этот фактический размер. "
            "Игнорируй любые старые числа, segment_refinement, top_120 и прошлые расчеты из истории задачи, если они отличаются от этого блока."
        )
    if is_first_assistant_reply and not seg_bound and is_director_handoff:
        prompt_parts.append(
            "Это поручение от AI Marketing Director. Не начинай с вопроса «какие данные есть» "
            "и не превращай ответ в обсуждение процесса. Выполни задачу в рамках своей роли и "
            "верни рабочий результат на согласование. Если данных не хватает, укажи это как "
            "проверку/риск, но всё равно предложи конкретную сегментацию, сценарий, критерии "
            "и статус передачи директору. Если первый расчёт не достигает целевого размера, KPI "
            "или формата результата, не останавливайся на констатации проблемы: предложи и сразу "
            "примени рабочее расширение/уточнение в рамках задачи, чтобы результат был пригоден "
            "для согласования администратором."
        )
    if prompt_agent_type == "assortment-agent":
        prompt_parts.append(
            "Ты AI Assortment с доступом к синхронизированной БД платформы GLAME. "
            "Не говори, что у тебя нет доступа к каталогу/остаткам/продажам, если в DATA-КОНТЕКСТЕ есть данные. "
            "Не проси прикрепить Excel/CSV. Используй реальные товары только из БД: product_id, external_id_1c, артикул, "
            "штрихкод, название, бренд, категорию, цену, наличие по магазинам/складам, продажи и чеки. "
            "Если данных в БД не хватает, назови конкретно: какая таблица/API пустая или какую синхронизацию нужно запустить."
        )
    elif is_first_assistant_reply and not seg_bound:
        prompt_parts.append(
            "Текущая задача еще не привязана к сегменту. Если запрос связан с CRM-рассылкой, "
            "сначала задай 3-5 уточняющих вопросов о цели рассылки, аудитории, бренде/городе/магазине, "
            "количестве получателей и дедлайне. После согласования предложи создать сегмент и описать критерии. "
            "Не создавай сегмент без явного подтверждения в следующем сообщении."
        )
    if context_text:
        prompt_parts.append(context_text)
    prompt_parts.append(f"Текущее сообщение пользователя:\n{body.message}")

    full_prompt = "\n\n".join(prompt_parts)
    deterministic_reply = _agent_identity_reply(task.target_agent) if is_identity_question else None

    auto_segment_created = None
    try:
        step = None
        if isinstance(body.metadata, ChatMetadata):
            step = body.metadata.step_type.value if body.metadata.step_type else None
        msg_l = (body.message or "").lower()
        need_segment = any(k in msg_l for k in ["сегмент", "сегментац", "база", "подготов", "сформиру", "создай"]) or step in {"segmentation"}
        if deterministic_reply:
            need_segment = False
        # Если сегмент уже привязан, чат должен работать строго по нему.
        # Пересборка доступна только через отдельные action endpoints с явным force_resegment.
        ctx_has_segment = bool(bound_segment_info)
        if ctx_has_segment:
            need_segment = False
        if is_first_assistant_reply and step not in {"segmentation"}:
            need_segment = False
        if need_segment:
            from app.models.customer_segment import CustomerSegment
            from app.models.user import User as UserModel
            from app.api.customer_segmentation import _build_select_for_rules
            segment_source_text = "\n".join([
                task_title or "",
                str((task.input_data or {}).get("description") or ""),
                str((task.input_data or {}).get("title") or ""),
                body.message or "",
            ])
            seg_rules = _extract_segment_rules_from_plan(segment_source_text, task_title)
            # Enrich with stores from message (handles Meganon + Centrum => OR)
            seg_rules = await _enrich_rules_with_stores(db, seg_rules, segment_source_text)
            segment_meta = _extract_segment_business_meta(segment_source_text)

            target = _extract_target_audience_size(body.message, task_title)
            base_stmt, _ = _build_select_for_rules(seg_rules)
            subq = base_stmt.subquery()
            count_res = await db.execute(select(func.count()).select_from(subq))
            count_val = int(count_res.scalar() or 0)
            if target:
                tuned = await _tune_rules_towards_target(db, dict(seg_rules), target, max_iters=5)
                seg_rules = tuned
                count_val = await _calc_count(db, seg_rules)
            recommended_segment = await _build_recommended_crm_segment_rules(db, segment_source_text, target, seg_rules)
            if recommended_segment:
                seg_rules, count_val, recommendation_meta = recommended_segment
                segment_meta["recommendation_expansion"] = recommendation_meta
            elif target and count_val > target:
                fresh_base_stmt, _ = _build_select_for_rules(seg_rules)
                ids_subq = fresh_base_stmt.subquery()
                top_ids_stmt = (
                    select(UserModel.id)
                    .where(UserModel.id.in_(select(ids_subq.c.id)))
                    .order_by(
                        UserModel.last_purchase_date.desc().nullslast(),
                        UserModel.total_purchases.desc(),
                        UserModel.total_spent.desc(),
                    )
                    .limit(target)
                )
                top_ids_res = await db.execute(top_ids_stmt)
                top_ids = [str(uid) for uid in top_ids_res.scalars().all()]
                if top_ids:
                    seg_rules = {"logic": "AND", "filters": [{"field": "id", "operator": "in", "value": top_ids}]}
                    count_val = len(top_ids)
            ctx = dict(task.task_context or {})
            seg_id_raw = ctx.get("segment_id")
            seg_obj = None
            if seg_id_raw:
                try:
                    seg_uuid = UUID(str(seg_id_raw))
                    row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
                    seg_obj = row.scalar_one_or_none()
                except Exception:
                    seg_obj = None
            if seg_obj and seg_obj.is_active:
                if segment_meta.get("name"):
                    seg_obj.name = _dedupe_segment_name(segment_meta["name"], str(seg_obj.id))
                seg_obj.description = _make_ai_segment_description(segment_meta, segment_source_text)
                seg_obj.rules = seg_rules
                seg_obj.customer_count = count_val
                seg_obj.updated_at = datetime.utcnow()
            else:
                seg_name = segment_meta.get("name") or _make_segment_name(task_id, task_title or "dialog")
                seg_obj = CustomerSegment(
                    id=uuid.uuid4(),
                    name=_dedupe_segment_name(seg_name, str(task_id)),
                    description=_make_ai_segment_description(segment_meta, segment_source_text),
                    rules=seg_rules,
                    customer_count=count_val,
                    is_auto_generated=True,
                    is_active=True,
                )
                db.add(seg_obj)
                await db.flush()
            count_val = await _save_segment_membership(db, seg_obj.id, seg_rules, assigned_by="ai", confidence_score=0.92)
            seg_obj.customer_count = count_val
            ctx["segment_id"] = str(seg_obj.id)
            ctx["segment_name"] = seg_obj.name
            ctx["segment_rules"] = seg_rules
            ctx["segment_meta"] = segment_meta
            ctx["segment_customer_count"] = count_val
            ctx["segment_edit_path"] = segment_meta.get("edit_path") or "/admin/customers/segments"
            task.task_context = ctx
            db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name=task.target_agent or "ai-marketer",
                    event_type="segmentation_completed",
                    event_data={
                        "segment_id": str(seg_obj.id),
                        "segment_name": seg_obj.name,
                        "customer_count": count_val,
                        "rules": seg_rules,
                        "meta": segment_meta,
                        "edit_path": ctx["segment_edit_path"],
                    },
                    message=f"AI CRM сохранил редактируемый сегмент: {seg_obj.name} ({count_val})",
                )
            )
            await db.commit()
            await db.refresh(task)
            await db.refresh(seg_obj)
            auto_segment_created = {"name": seg_obj.name, "count": count_val}

            # Inject segment result into the prompt so the agent knows about it!
            full_prompt += f"\n\n[SYSTEM UPDATE]\nАвтоматически создан/обновлен сегмент '{seg_obj.name}'.\n"
            full_prompt += f"Количество покупателей: {count_val}.\n"
            full_prompt += "Сегмент уже сохранен в БД и виден в «Покупатели → Сегменты покупателей»; пользователь может редактировать фильтры вручную или вернуть сегмент тебе на доработку.\n"
            if count_val == 0:
                full_prompt += "ВНИМАНИЕ: В сегменте 0 покупателей! Ты ОБЯЗАН сообщить об этом пользователю и предложить убрать часть фильтров (например, расширить географию или период покупок).\n"
            elif target and count_val < target * 0.5:
                full_prompt += f"ВНИМАНИЕ: Найдено меньше покупателей, чем ожидалось ({target}). Предложи расширить критерии.\n"

    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        auto_segment_created = None

    # 4. Генерация ответа
    try:
        model_to_use = None
        if isinstance(body.model, str) and "/" in body.model:
            model_to_use = body.model
        if deterministic_reply:
            reply = deterministic_reply
        else:
            reply = await generate_agent_text(
                agent_id=task.target_agent,
                prompt=full_prompt,
                model=model_to_use,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=4200,
            )
        if not isinstance(reply, str) or not reply.strip():
            reply = (
                f"{task_agent_name} не вернул содержательный ответ от AI-ядра. "
                "Это технический статус, а не результат выполнения задачи. "
                "Сообщение пользователя сохранено в чате; задачу нужно повторить после проверки модели/runtime."
            )
        elif _looks_truncated_reply(reply):
            continuation = await generate_agent_text(
                agent_id=task.target_agent,
                prompt=(
                    f"{full_prompt}\n\n"
                    "Предыдущий ответ агента был обрезан. Продолжи строго с места остановки, "
                    "не повторяй уже написанное, заверши недостающие пункты и финальный статус для директора.\n\n"
                    f"Обрезанный ответ:\n{reply[-1800:]}"
                ),
                model=model_to_use,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=1800,
            )
            if isinstance(continuation, str) and continuation.strip():
                reply = f"{reply.rstrip()}\n\n{continuation.strip()}"
    except Exception as e:
        reply = (
            f"{task_agent_name} сейчас не получил ответ от AI-ядра. "
            "Это технический статус, а не рабочий результат агента. "
            "Сообщение в чате сохранено, задачу не закрываю.\n\n"
            f"Техническая причина: {str(e)}\n\n"
            "Проверьте авторизацию/модель профиля Hermes для этого агента или переключите ИИ-ядро в настройках."
        )
        err_log = AgentInteractionLog(
            task_id=task_id,
            agent_name=task_agent_name,
            event_type="error",
            event_data={
                "stage": "llm_generate",
                "normalized_model": (body.model or "default"),
                "metadata": (body.metadata.dict(exclude_none=True) if isinstance(body.metadata, ChatMetadata) else (body.metadata or {})),
                "error": str(e),
            },
            message="Ошибка генерации ответа агента",
        )
        db.add(err_log)
        await db.flush()

    if bound_segment_info and not deterministic_reply:
        seg_block = (
            f"## Анализ выбранного сегмента\n"
            f"- Сегмент: {bound_segment_info['name']}\n"
            f"- ID сегмента: `{bound_segment_info['id']}`\n"
            f"- Фактический размер по правилам БД: {bound_segment_info['count']} покупателей\n"
            f"- В работе используется только этот выбранный сегмент; другие сегменты и ранее созданные дубли не применялись.\n"
            f"- Для предпросмотра используйте кнопку «Предпросмотр сегмента» в интерфейсе задачи.\n\n"
        )
        reply = seg_block + reply
    elif auto_segment_created and not deterministic_reply:
        seg_block = (
            f"## Анализ и сегментация аудитории\n"
            f"- Фактически сохранено в БД: {auto_segment_created['name']} ({auto_segment_created['count']} покупателей)\n"
            f"- Это единственный достоверный размер сегмента для этой версии. Если ниже в тексте есть другая цифра, считать её недействительной.\n"
            f"- Чтобы внести правки, напишите сообщение в стиле: «оставь только женщины 25–45», "
            f"«исключи без покупок 180+», «город Симферополь» и т. п.\n"
            f"- Для предпросмотра используйте кнопку «Предпросмотр сегмента» в интерфейсе задачи.\n\n"
        )
        reply = seg_block + reply

    qa_check = None if deterministic_reply else _evaluate_agent_reply_quality(reply, task if is_director_handoff else None, auto_segment_created or bound_segment_info)
    if qa_check and qa_check.get("needs_revision"):
        director_revision_prompt = qa_check["revision_prompt"]
        db.add(
            AgentInteractionLog(
                task_id=task.id,
                agent_name=task_agent_name,
                event_type="dialog_message",
                event_data={"kind": "assistant_draft", "role": "assistant", "qa_status": "needs_revision"},
                message=reply,
            )
        )
        db.add(
            AgentInteractionLog(
                task_id=task.id,
                agent_name="director-agent",
                event_type="dialog_message",
                event_data={"role": "user", "from_director": True, "qa_revision": True},
                message=director_revision_prompt,
            )
        )
        try:
            revised_reply = await generate_agent_text(
                agent_id=task.target_agent,
                prompt=(
                    f"{full_prompt}\n\n"
                    "=== ЧЕРНОВОЙ ОТВЕТ АГЕНТА ===\n"
                    f"{reply}\n\n"
                    "=== ПРОВЕРКА AI MARKETING DIRECTOR ===\n"
                    f"{director_revision_prompt}\n\n"
                    "Дай исправленный финальный ответ агенту/директору. Не обсуждай процесс проверки, "
                    "а верни готовый результат в рабочем виде для согласования администратором."
                ),
                model=model_to_use,
                system_prompt=system_prompt,
                temperature=0.45,
                max_tokens=3200,
            )
            if isinstance(revised_reply, str) and revised_reply.strip():
                reply = revised_reply.strip()
        except Exception:
            logger.warning("Director QA revision request failed", exc_info=True)
        if bound_segment_info:
            factual_block = (
                f"## Фактический результат из БД\n"
                f"- Сегмент: {bound_segment_info['name']}\n"
                f"- ID сегмента: `{bound_segment_info['id']}`\n"
                f"- Размер: {bound_segment_info['count']} покупателей\n"
                f"- Это выбранный сегмент задачи; другие сегменты в ответе не являются рабочими.\n\n"
            )
            if "## Фактический результат из БД" not in reply:
                reply = factual_block + reply
        elif auto_segment_created:
            factual_block = (
                f"## Фактический результат из БД\n"
                f"- Сегмент: {auto_segment_created['name']}\n"
                f"- Размер: {auto_segment_created['count']} покупателей\n"
                f"- Состав сегмента сохранен в `user_segments`; предпросмотр и выгрузка должны показывать этот список.\n"
                f"- Любые другие числа в тексте ответа не являются результатом расчета.\n\n"
            )
            if "## Фактический результат из БД" not in reply:
                reply = factual_block + reply

    closure = None if deterministic_reply else _evaluate_director_task_closure(reply, is_director_handoff)
    if closure:
        task.output_data = {
            **(task.output_data or {}),
            "agent_reply": reply,
            "result_summary": closure["summary"],
            "needs_user_attention": closure["needs_user_attention"],
        }
        task.output_metadata = {
            **(task.output_metadata or {}),
            "closed_by": "director-auto-monitor",
            "closure_reason": closure["reason"],
            "closure_status": closure["status"],
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        if closure["status"] == InteractionStatus.COMPLETED.value:
            task.status = InteractionStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
        elif closure["status"] == InteractionStatus.PENDING_APPROVAL.value:
            task.status = InteractionStatus.PENDING_APPROVAL.value
        else:
            task.status = InteractionStatus.PROCESSING.value

    # 5. Логируем и индексируем ответ агента
    assistant_log = AgentInteractionLog(
        task_id=task_id,
        agent_name=task_agent_name,
        event_type="dialog_message",
        event_data={
            "kind": "assistant_reply",
            "normalized_model": (model_to_use or "default"),
            **(body.metadata.dict(exclude_none=True) if isinstance(body.metadata, ChatMetadata) else (body.metadata or {})),
        },
        message=reply,
    )
    db.add(assistant_log)
    mirror_agent_task_turn_to_hermes_web_ui(
        agent_id=task.target_agent,
        task_id=str(task.id),
        task_title=task_title or task.task_type or "GLAME task",
        user_message=body.message,
        assistant_response=reply,
        model=model_to_use or (body.model if isinstance(body.model, str) else None),
    )
    if closure:
        db.add(
            AgentInteractionLog(
                task_id=task.id,
                agent_name="director-auto-monitor",
                event_type="task_closure_evaluated",
                event_data=closure,
                message=closure["summary"],
            )
        )
    await db.commit()
    await db.refresh(assistant_log)
    assistant_log_id_str = str(assistant_log.id)

    try:
        vector_service.add_text_document(
            collection_name="task_dialogs",
            text=f"[assistant] {reply}",
            metadata={
                "task_id": task_id_str,
                "role": "assistant",
                "log_id": assistant_log_id_str,
                "created_at": assistant_log.created_at.isoformat() if assistant_log.created_at else None,
                **(body.metadata.dict(exclude_none=True) if isinstance(body.metadata, ChatMetadata) else (body.metadata or {})),
            },
        )
    except Exception:
        logger = logging.getLogger(__name__)
        logger.warning("Failed to index assistant dialog message into vector DB", exc_info=True)

    return ChatWithAgentResponse(
        reply=reply,
        used_brand_context=brand_context,
        used_history_fragments=history_fragments,
        user_log_id=user_log_id_str,
        assistant_log_id=assistant_log_id_str,
    )

@router.delete("/tasks/{task_id}/chat/{log_id}")
async def delete_task_chat_message(
    task_id: UUID,
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    res = await db.execute(
        select(AgentInteractionLog).where(
            and_(
                AgentInteractionLog.id == log_id,
                AgentInteractionLog.task_id == task.id,
                AgentInteractionLog.event_type == "dialog_message",
            )
        )
    )
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    try:
        delete_task_dialog_by_log_id(str(log.id))
    except Exception:
        pass
    await db.delete(log)
    await db.commit()
    return {"status": "deleted", "id": str(log_id)}
@router.get("/tasks/{task_id}/audit", response_model=InteractionChainResponse)
async def get_interaction_audit_chain(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение полной цепочки взаимодействия для аудита"""
    service = AgentInteractionService(db)

    try:
        chain = await service.get_interaction_chain(str(task_id))
        return InteractionChainResponse(**chain)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Endpoints для управления правилами валидации
# ============================================================================

@router.post("/validation-rules", response_model=ValidationRuleResponse)
async def create_validation_rule(
    request: CreateValidationRuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создание правила валидации (требуется аутентификация)"""
    service = AgentInteractionService(db)

    rule = await service.create_validation_rule(
        task_type=request.task_type,
        rule_name=request.rule_name,
        rule_description=request.rule_description,
        validation_schema=request.validation_schema,
        validation_function=request.validation_function,
        source_agent=request.source_agent,
        target_agent=request.target_agent,
        is_required=request.is_required,
        error_message=request.error_message,
        priority=request.priority
    )

    return ValidationRuleResponse(
        id=str(rule.id),
        task_type=rule.task_type,
        rule_name=rule.rule_name,
        rule_description=rule.rule_description,
        source_agent=rule.source_agent,
        target_agent=rule.target_agent,
        is_required=rule.is_required,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat() if rule.created_at else None
    )


@router.get("/validation-rules", response_model=List[ValidationRuleResponse])
async def list_validation_rules(
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    is_active: Optional[bool] = Query(None, description="Фильтр по статусу активности"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка правил валидации"""
    service = AgentInteractionService(db)

    rules = await service.get_validation_rules(task_type, is_active)

    return [
        ValidationRuleResponse(
            id=str(r.id),
            task_type=r.task_type,
            rule_name=r.rule_name,
            rule_description=r.rule_description,
            source_agent=r.source_agent,
            target_agent=r.target_agent,
            is_required=r.is_required,
            is_active=r.is_active,
            priority=r.priority,
            created_at=r.created_at.isoformat() if r.created_at else None
        )
        for r in rules
    ]


@router.get("/validation-rules/{rule_id}", response_model=ValidationRuleResponse)
async def get_validation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получение деталей правила валидации"""
    result = await db.execute(
        select(AgentValidationRule).where(AgentValidationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")


# ============================================================================
# Endpoints для системы эскалации просроченных задач
# ============================================================================

@router.post("/tasks/escalate/check", response_model=List[AgentTaskResponse])
async def check_and_escalate_overdue_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Запуск проверки и эскалации всех просроченных задач согласно Enterprise Blueprint.
    Требуются права администратора или AI Marketing Director.
    """
    allowed_roles = ("admin", "ai_marketer", "content_manager")
    if str(getattr(current_user, "role", "") or "") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав для запуска эскалации")

    service = AgentInteractionService(db)
    escalated_tasks = await service.check_and_escalate_overdue_tasks()

    return [
        AgentTaskResponse(
            id=str(t.id),
            source_agent=t.source_agent,
            target_agent=t.target_agent,
            task_type=t.task_type,
            task_context=t.task_context or {},
            input_data=t.input_data or {},
            target_metrics=t.target_metrics or {},
            requirements=t.requirements or {},
            constraints=t.constraints or {},
            status=t.status,
            priority=t.priority,
            validation_result=t.validation_result,
            validation_errors=t.validation_errors or [],
            output_data=t.output_data,
            output_metadata=t.output_metadata or {},
            error_message=t.error_message,
            created_at=t.created_at.isoformat() if t.created_at else None,
            scheduled_at=t.scheduled_at.isoformat() if t.scheduled_at else None,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            deadline_at=t.deadline_at.isoformat() if t.deadline_at else None,
        )
        for t in escalated_tasks
    ]


@router.get("/tasks/escalate/stats", response_model=Dict[str, Any])
async def get_overdue_tasks_stats(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение статистики по просроченным задачам для отображения на дашборде"""
    service = AgentInteractionService(db)
    return await service.get_overdue_tasks_stats()

    return ValidationRuleResponse(
        id=str(rule.id),
        task_type=rule.task_type,
        rule_name=rule.rule_name,
        rule_description=rule.rule_description,
        source_agent=rule.source_agent,
        target_agent=rule.target_agent,
        is_required=rule.is_required,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat() if rule.created_at else None
    )


@router.patch("/validation-rules/{rule_id}/toggle")
async def toggle_validation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Включение/выключение правила валидации"""
    result = await db.execute(
        select(AgentValidationRule).where(AgentValidationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")

    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)

    return {
        "message": f"Правило {'активировано' if rule.is_active else 'деактивировано'}",
        "rule_id": str(rule.id),
        "is_active": rule.is_active
    }


class MassMailingPrepareRequest(BaseModel):
    plan_text: str
    plan_title: Optional[str] = None
    brand: Optional[str] = None
    event_type: Optional[str] = None
    message_count: Optional[int] = Field(None, ge=1, le=5000)
    metadata: Optional[Dict[str, Any]] = None


class MassMailingSegmentInfo(BaseModel):
    id: str
    name: str
    customer_count: int


class MassMailingSuggestedRequest(BaseModel):
    brand: Optional[str] = None
    limit: int
    auto_detect_store: bool = True
    event: Dict[str, Any]
    search_criteria: Dict[str, Any]


class MassMailingPrepareResponse(BaseModel):
    report: str
    segment: MassMailingSegmentInfo
    suggested_request: MassMailingSuggestedRequest


class MassMailingRunRequest(BaseModel):
    segment_id: str
    event_type: str
    brand: Optional[str] = None
    message_count: int = Field(25, ge=1, le=5000)
    auto_detect_store: bool = True
    metadata: Optional[Dict[str, Any]] = None


class MassMailingRunResponse(BaseModel):
    report: str
    segment: MassMailingSegmentInfo
    generation_id: str
    events_url: str


class BindSegmentRequest(BaseModel):
    segment_id: str


def _derive_mass_event_type(plan_title: Optional[str], plan_text: str) -> str:
    t = (plan_title or "").strip()
    p = (plan_text or "").strip()
    src = f"{t}\n{p}".lower()
    if "8 марта" in src and ("sms" in src or "смс" in src):
        return "sms_8_march"
    if "sms" in src or "смс" in src:
        return "sms_broadcast"
    if "рассыл" in src:
        return "broadcast"
    return "mass_mailing"


def _derive_message_count(plan_text: str, fallback: int = 100) -> int:
    import re

    m = re.search(r"\b(\d{1,5})\s*(сообщен|sms|смс)\w*\b", (plan_text or "").lower())
    if not m:
        return fallback
    try:
        v = int(m.group(1))
        if v < 1:
            return fallback
        if v > 5000:
            return 5000
        return v
    except Exception:
        return fallback


def _make_segment_name(task_id: UUID, plan_title: Optional[str]) -> str:
    import re
    from datetime import datetime as _dt

    base = (plan_title or "").strip()
    if not base:
        base = "mass-mailing"
    base = re.sub(r"\s+", " ", base)
    base = re.sub(r"[^0-9A-Za-zА-Яа-я _\\-]+", "", base)
    base = base.strip().replace(" ", "_")
    ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"auto_{str(task_id)[:8]}_{ts}_{base}"
    if len(name) > 100:
        name = name[:100]
    return name


def _clean_segment_name_part(value: Optional[str]) -> str:
    part = (value or "").strip()
    part = re.sub(r"\s+", " ", part)
    part = re.sub(r"[^0-9A-Za-zА-Яа-яЁё _\\-|]+", "", part)
    return part.strip(" _-|")


def _dedupe_segment_name(name: str, suffix: Optional[str] = None) -> str:
    """Build a stable, UI-readable segment name; DB-level uniqueness is handled by timestamp/suffix."""
    base = _clean_segment_name_part(name) or "AI CRM сегмент"
    if suffix:
        short = str(suffix).replace("-", "")[:6]
        if short and short.lower() not in base.lower():
            base = f"{base} · {short}"
    if len(base) > 100:
        base = base[:100].rstrip(" _-|·")
    return base


def _extract_city_from_text(text: str) -> Optional[str]:
    src = (text or "").lower()
    known_cities = {
        "симферопол": "Симферополь",
        "ялт": "Ялта",
        "севастопол": "Севастополь",
    }
    for marker, city in known_cities.items():
        if marker in src:
            return city
    return None


def _normalize_brand(value: str) -> Optional[str]:
    raw = (value or "").strip(" .,:;()[]{}«»\"'")
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return None
    stop_words = {
        "бренд", "бренда", "бренду", "поступление", "поступления", "новинки", "новое",
        "конкретно", "этот", "этого", "для", "клиентов", "покупателей", "симферополя",
        "рассылки", "сегмента", "сегмент",
    }
    if raw.lower() in stop_words or len(raw) < 2:
        return None
    return raw


def _extract_brand_from_text(text: str) -> Optional[str]:
    original = text or ""
    src = original.lower()
    known_brands = [
        "UNOde50", "UNO de 50", "Unode50", "Pandora", "Swarovski", "Tous",
        "Sokolov", "Thomas Sabo", "Nomination", "Guess", "Calvin Klein",
    ]
    compact_src = re.sub(r"[\s_\-]+", "", src)
    for brand in known_brands:
        compact_brand = re.sub(r"[\s_\-]+", "", brand.lower())
        if compact_brand and compact_brand in compact_src:
            return "UNOde50" if compact_brand == "unode50" else brand

    patterns = [
        r"(?:бренд[а-яё]*|марка|поступлен[а-яё]*|новинк[а-яё]*)\s+(?:бренда\s+)?([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 _\-]{1,40})",
        r"(?:интерес[а-яё\s]*к)\s+([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 _\-]{1,40})",
    ]
    for pattern in patterns:
        m = re.search(pattern, original, re.IGNORECASE)
        if not m:
            continue
        candidate = re.split(
            r"\s+(?:для|по|в|на|и|с|котор|поступлен|новинк|рассыл|сегмент)",
            m.group(1).strip(),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        brand = _normalize_brand(candidate)
        if brand:
            return brand
    return None


def _extract_segment_business_meta(text: str) -> Dict[str, Any]:
    brand = _extract_brand_from_text(text)
    city = _extract_city_from_text(text)
    src = (text or "").lower()
    if "whatsapp" in src or "wa" in src:
        channel = "WhatsApp"
    elif "sms" in src or "смс" in src:
        channel = "SMS"
    elif "push" in src or "пуш" in src:
        channel = "Push"
    elif "email" in src or "почт" in src:
        channel = "Email"
    else:
        channel = None

    purpose_bits = []
    if brand:
        purpose_bits.append(brand)
    if city:
        purpose_bits.append(city)
    if "first look" in src or "firstlook" in src or "перв" in src:
        purpose_bits.append("First Look")
    elif "рассыл" in src:
        purpose_bits.append("рассылка")
    if channel:
        purpose_bits.append(channel)

    ts = datetime.utcnow().strftime("%d.%m %H:%M")
    name = "AI CRM | " + " | ".join(purpose_bits or ["сегмент на согласование"])
    name = f"{name} | {ts}"
    return {
        "brand": brand,
        "city": city,
        "channel": channel,
        "name": _dedupe_segment_name(name),
        "edit_path": "/admin/customers/segments",
    }


def _make_ai_segment_description(meta: Dict[str, Any], source_text: str) -> str:
    details = []
    if meta.get("brand"):
        details.append(f"бренд: {meta['brand']}")
    if meta.get("city"):
        details.append(f"город/магазин: {meta['city']}")
    if meta.get("channel"):
        details.append(f"канал: {meta['channel']}")
    details_text = "; ".join(details) if details else "критерии извлечены из задачи директора"
    short_source = re.sub(r"\s+", " ", (source_text or "").strip())[:500]
    return (
        "AI CRM: сегмент создан по поручению AI Marketing Director и доступен для "
        f"редактирования в «Покупатели → Сегменты покупателей». Критерии: {details_text}. "
        f"Исходная задача: {short_source}"
    )


def _crm_task_passport_text(task: AgentInteractionTask) -> str:
    input_data = task.input_data or {}
    task_context = task.task_context or {}
    requirements = task.requirements or {}
    constraints = task.constraints or {}
    parts = [
        str(input_data.get("title") or task_context.get("title") or task.task_type or ""),
        str(input_data.get("description") or ""),
        str(input_data.get("expected_result") or ""),
        str(task_context.get("original_user_request") or ""),
    ]
    if requirements:
        parts.append(json.dumps(requirements, ensure_ascii=False, default=str))
    if constraints:
        parts.append(json.dumps(constraints, ensure_ascii=False, default=str))
    return "\n\n".join(p for p in parts if p and p != "{}").strip()


def _should_auto_run_crm_passport(task: AgentInteractionTask, source_text: str, updated_fields: List[str]) -> bool:
    target_agent = _prompt_agent_id(task.target_agent or "")
    if target_agent != "crm-agent":
        return False
    if not any(field in {"task_context", "input_data", "requirements", "constraints", "target_metrics", "status"} for field in updated_fields):
        return False
    src = (source_text or "").lower()
    return any(k in src for k in ["сегмент", "сегментац", "рассыл", "покупател", "клиент", "crm", "аудитор"])


def _json_stable(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value or "")


def _should_start_dialog_from_passport_update(
    previous: Dict[str, Any],
    task: AgentInteractionTask,
    updated_fields: List[str],
) -> bool:
    if not any(field in {"task_type", "input_data", "requirements", "constraints", "target_metrics"} for field in updated_fields):
        return False
    current = task.to_dict()
    for key in ("task_type", "input_data", "requirements", "constraints", "target_metrics"):
        if _json_stable(previous.get(key)) != _json_stable(current.get(key)):
            return True
    return False


async def _append_passport_update_dialog_request(
    db: AsyncSession,
    task: AgentInteractionTask,
    actor_name: str,
    updated_fields: List[str],
) -> None:
    source_text = _crm_task_passport_text(task)
    if not source_text:
        return

    dialog_run_id = str(uuid.uuid4())
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    task_ctx = dict(task.task_context or {})
    task_ctx.update(
        {
            "dialog_run_id": dialog_run_id,
            "dialog_started_at": datetime.utcnow().isoformat(),
            "dialog_started_by": actor_name,
            "passport_source_hash": source_hash,
            "passport_update_pending_agent_reply": True,
        }
    )
    task.task_context = task_ctx

    message = (
        "AI Marketing Director обновил паспорт задачи. Воспринимай это как новое уточнение/поручение, "
        "а не как справочную правку. Нужно ответить по обновленному описанию, пересмотреть выводы и, "
        "если нужны данные, явно указать какие данные нужно обновить или синхронизировать.\n\n"
        f"{source_text}"
    )
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="system",
            event_type="chat_reset",
            event_data={
                "dialog_run_id": dialog_run_id,
                "reason": "task_passport_updated",
                "updated_fields": updated_fields,
                "source_hash": source_hash,
            },
            message="Паспорт обновлен: начат новый чат задачи",
        )
    )
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="director-agent",
            event_type="dialog_message",
            event_data={
                "role": "user",
                "from_director": True,
                "step_type": "other",
                "dialog_run_id": dialog_run_id,
                "source": "task_passport",
                "requires_agent_reply": True,
            },
            message=message,
        )
    )


def _append_filter_to_and(rules: Dict[str, Any], filter_obj: Dict[str, Any]) -> Dict[str, Any]:
    if rules.get("logic") != "AND":
        rules = {"logic": "AND", "filters": [rules]}
    filters = list(rules.get("filters") or [])
    filters.append(filter_obj)
    rules["filters"] = filters
    return rules


async def _limit_segment_rules_to_top_customers(
    db: AsyncSession,
    rules: Dict[str, Any],
    target: Optional[int],
) -> tuple[Dict[str, Any], int]:
    from app.api.customer_segmentation import _build_select_for_rules
    from app.models.user import User as UserModel

    count_val = await _calc_count(db, rules)
    if not target:
        return rules, count_val
    if count_val > target:
        base_stmt, _ = _build_select_for_rules(rules)
        ids_subq = base_stmt.subquery()
        top_ids_stmt = (
            select(UserModel.id)
            .where(UserModel.id.in_(select(ids_subq.c.id)))
            .order_by(
                UserModel.last_purchase_date.desc().nullslast(),
                UserModel.total_purchases.desc(),
                UserModel.total_spent.desc(),
            )
            .limit(target)
        )
        top_ids_res = await db.execute(top_ids_stmt)
        top_ids = [str(uid) for uid in top_ids_res.scalars().all()]
        if top_ids:
            return {"logic": "AND", "filters": [{"field": "id", "operator": "in", "value": top_ids}]}, len(top_ids)
    return rules, count_val


def _build_crm_segment_result_reply(
    task_id: str,
    segment_name: str,
    segment_id: str,
    count_val: int,
    rules: Dict[str, Any],
    target: Optional[int],
    initial_count: int,
    source_text: str,
) -> str:
    target_line = f"{target} покупателей" if target else "целевой размер не указан"
    rules_json = json.dumps(rules, ensure_ascii=False, default=str)
    warnings = []
    if target and count_val < target:
        warnings.append(
            f"Размер ниже цели: найдено {count_val} из {target}. Нужно согласовать расширение критериев или более широкий период/географию."
        )
    if not warnings:
        warnings.append("Перед отправкой проверить согласия на канал коммуникации и финальный список исключений.")
    source_short = re.sub(r"\s+", " ", source_text or "").strip()[:420]
    return (
        "## AI CRM: сегмент подготовлен\n\n"
        f"1. Данные использованы: карточки покупателей, история покупок, предпочтительный магазин/город, бренд и товарные признаки из чеков.\n"
        f"2. Сегмент сохранен в БД: `{segment_name}`\n"
        f"3. ID сегмента: `{segment_id}`\n"
        f"4. Размер сегмента: {count_val} покупателей. Цель: {target_line}. Первичный фильтр дал {initial_count}.\n"
        f"5. Где редактировать: `/admin/customers/segments` или карточка задачи `/ai-marketer/tasks/{task_id}`.\n\n"
        "### Правила сегмента\n"
        f"```json\n{rules_json}\n```\n\n"
        "### Риски и согласование\n"
        + "\n".join(f"- {w}" for w in warnings)
        + "\n\nСтатус: сегмент готов для карточки директора и согласования администратором. "
        f"Исходная формулировка: {source_short}"
    )


async def _auto_prepare_crm_segment_from_task_passport(
    db: AsyncSession,
    task: AgentInteractionTask,
    actor_name: str,
    updated_fields: List[str],
) -> Optional[Dict[str, Any]]:
    source_text = _crm_task_passport_text(task)
    if not _should_auto_run_crm_passport(task, source_text, updated_fields):
        return None

    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    task_ctx = dict(task.task_context or {})
    dialog_run_id = str(uuid.uuid4())

    from app.models.customer_segment import CustomerSegment

    segment_meta = _extract_segment_business_meta(source_text)
    segment_rules = _extract_segment_rules_from_plan(source_text, str((task.input_data or {}).get("title") or ""))
    segment_rules = await _enrich_rules_with_stores(db, segment_rules, source_text)
    target_size = _extract_target_audience_size(source_text, str((task.input_data or {}).get("title") or ""))
    initial_count = await _calc_count(db, segment_rules)
    if target_size:
        tuned = await _tune_rules_towards_target(db, dict(segment_rules), target_size, max_iters=5)
        segment_rules = tuned
    recommended_segment = await _build_recommended_crm_segment_rules(db, source_text, target_size, segment_rules)
    if recommended_segment:
        segment_rules, count_val, recommendation_meta = recommended_segment
        segment_meta["recommendation_expansion"] = recommendation_meta
    else:
        segment_rules, count_val = await _limit_segment_rules_to_top_customers(db, segment_rules, target_size)

    segment_name = segment_meta.get("name") or _make_segment_name(task.id, (task.input_data or {}).get("title"))
    seg_obj = None
    if task_ctx.get("segment_id"):
        try:
            seg_uuid = UUID(str(task_ctx.get("segment_id")))
            row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
            existing = row.scalar_one_or_none()
            if existing and bool(getattr(existing, "is_auto_generated", True)):
                seg_obj = existing
        except Exception:
            seg_obj = None

    if seg_obj:
        seg_obj.name = _dedupe_segment_name(segment_name, str(seg_obj.id))
        seg_obj.description = _make_ai_segment_description(segment_meta, source_text)
        seg_obj.rules = segment_rules
        seg_obj.customer_count = count_val
        seg_obj.updated_at = datetime.utcnow()
    else:
        seg_obj = CustomerSegment(
            id=uuid.uuid4(),
            name=_dedupe_segment_name(segment_name, str(task.id)),
            description=_make_ai_segment_description(segment_meta, source_text),
            rules=segment_rules,
            customer_count=count_val,
            is_auto_generated=True,
            is_active=True,
        )
        db.add(seg_obj)
        await db.flush()

    count_val = await _save_segment_membership(db, seg_obj.id, segment_rules, assigned_by="ai", confidence_score=0.92)
    seg_obj.customer_count = count_val

    task_ctx.update(
        {
            "dialog_run_id": dialog_run_id,
            "dialog_started_at": datetime.utcnow().isoformat(),
            "dialog_started_by": actor_name,
            "passport_source_hash": source_hash,
            "segment_id": str(seg_obj.id),
            "segment_name": seg_obj.name,
            "segment_rules": segment_rules,
            "segment_meta": segment_meta,
            "segment_customer_count": count_val,
            "segment_initial_customer_count": initial_count,
            "segment_edit_path": segment_meta.get("edit_path") or "/admin/customers/segments",
        }
    )
    task.task_context = task_ctx

    handoff_message = (
        "AI Marketing Director передал обновленный паспорт как новую задачу AI CRM.\n\n"
        f"{source_text}"
    )
    reply = _build_crm_segment_result_reply(
        task_id=str(task.id),
        segment_name=seg_obj.name,
        segment_id=str(seg_obj.id),
        count_val=count_val,
        rules=segment_rules,
        target=target_size,
        initial_count=initial_count,
        source_text=source_text,
    )

    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="system",
            event_type="chat_reset",
            event_data={
                "dialog_run_id": dialog_run_id,
                "reason": "task_passport_updated",
                "updated_fields": updated_fields,
                "source_hash": source_hash,
            },
            message="Паспорт обновлен: начат новый чат задачи AI CRM",
        )
    )
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="director-agent",
            event_type="dialog_message",
            event_data={
                "role": "user",
                "from_director": True,
                "step_type": "segmentation",
                "dialog_run_id": dialog_run_id,
                "source": "task_passport",
            },
            message=handoff_message,
        )
    )
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name=task.target_agent or "crm-agent",
            event_type="dialog_message",
            event_data={
                "kind": "assistant_reply",
                "role": "assistant",
                "from_agent": task.target_agent or "crm-agent",
                "dialog_run_id": dialog_run_id,
                "segment_id": str(seg_obj.id),
                "segment_name": seg_obj.name,
            },
            message=reply,
        )
    )
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name=task.target_agent or "crm-agent",
            event_type="segmentation_completed",
            event_data={
                "dialog_run_id": dialog_run_id,
                "segment_id": str(seg_obj.id),
                "segment_name": seg_obj.name,
                "customer_count": count_val,
                "initial_customer_count": initial_count,
                "rules": segment_rules,
                "meta": segment_meta,
                "edit_path": task_ctx["segment_edit_path"],
                "source_hash": source_hash,
            },
            message=f"AI CRM сохранил редактируемый сегмент: {seg_obj.name} ({count_val})",
        )
    )
    return {
        "segment_id": str(seg_obj.id),
        "segment_name": seg_obj.name,
        "customer_count": count_val,
        "initial_customer_count": initial_count,
        "rules": segment_rules,
        "reply": reply,
    }


def _looks_truncated_reply(reply: str) -> bool:
    """Эвристика: ответ модели оборвался на середине мысли и требует автопродолжения."""
    text_value = (reply or "").rstrip()
    if not text_value:
        return False

    tail = text_value[-260:].lower()
    complete_markers = [
        "готов передать",
        "можно передавать",
        "нельзя передавать",
        "статус для директора",
        "следующий шаг",
        "итог:",
        "результат:",
    ]
    if any(marker in tail for marker in complete_markers) and text_value[-1:] in ".!?…":
        return False

    if text_value[-1:] not in ".!?…):»”]":
        return True
    if re.search(r"\b(логи|сегментационн|коммуникационн|администратор|директор|согласованн|предварительн)$", tail):
        return True
    if tail.endswith(("-", "—", ":", ",")):
        return True
    return False


def _evaluate_agent_reply_quality(
    reply: str,
    task: Optional[AgentInteractionTask],
    auto_segment_created: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Проверка директора: агент должен вернуть не проблему, а пригодный к согласованию результат."""
    if task is None:
        return None

    text_value = (reply or "").strip()
    lower = text_value.lower()
    task_type = (task.task_type or "").lower()
    title = str((task.input_data or {}).get("title") or (task.task_context or {}).get("title") or "")
    description = str((task.input_data or {}).get("description") or "")
    expected = str((task.input_data or {}).get("expected_result") or "")
    assignment = f"{title}\n{description}\n{expected}".lower()

    problems: List[str] = []
    revision_bits: List[str] = []

    if not text_value:
        problems.append("агент вернул пустой ответ")
    if len(text_value) < 220:
        problems.append("ответ слишком короткий и не раскрывает решение задачи")

    segment_locked_for_task = bool((task.task_context or {}).get("selected_segment_locked"))
    generic_deferral_markers = [
        "нужно открыть",
        "необходимо открыть",
        "добавить условия вручную",
        "точный список формирует",
        "способ пересчета",
        "прогнозируемый размер",
    ]
    if not segment_locked_for_task:
        generic_deferral_markers.extend(["предлагаю расширить", "рекомендуется утвердить расширение"])
    if any(marker in lower for marker in generic_deferral_markers):
        problems.append("агент переложил доработку на пользователя вместо готового результата")

    if "crm" in task_type or "сегмент" in assignment or "рассыл" in assignment:
        segment_count = None
        segment_locked = segment_locked_for_task
        try:
            if auto_segment_created:
                segment_count = int(auto_segment_created.get("count") or 0)
            elif (task.task_context or {}).get("segment_customer_count") is not None:
                segment_count = int((task.task_context or {}).get("segment_customer_count") or 0)
        except Exception:
            segment_count = None
        target_match = re.search(r"(\d{2,5})\s*[-–—]\s*(\d{2,5})\s*(?:человек|клиент|покупател)", assignment)
        target_min = int(target_match.group(1)) if target_match else None
        if segment_count is not None and target_min and segment_count < target_min and not segment_locked:
            problems.append(f"сегмент меньше целевого диапазона: {segment_count} < {target_min}")
            revision_bits.append(
                f"Текущий сегмент слишком маленький ({segment_count}). Самостоятельно расширь критерии "
                f"до минимум {target_min} релевантных покупателей, обнови сохраненный сегмент и верни финальный вариант."
            )
        if "id/" not in lower and "сегмент:" not in lower and "название сегмента" not in lower:
            problems.append("не указан сохраненный сегмент или место редактирования")
        if "риск" not in lower:
            problems.append("не указаны риски перед запуском")
        if "соглас" not in lower:
            problems.append("нет явного статуса согласования")

    if "analytics" in task_type or "аналит" in assignment or "отчет" in assignment or "отчёт" in assignment:
        if not any(word in lower for word in ["вывод", "kpi", "метрик", "данн", "период"]):
            problems.append("аналитический ответ без вывода, периода, данных или KPI")

    if "assortment" in task_type or "product" in task_type or "ассортимент" in assignment or "sku" in assignment:
        if not any(word in lower for word in ["sku", "остат", "товар", "категор", "риск"]):
            problems.append("товарный ответ без SKU/остатков/товарных критериев/рисков")

    if "content" in task_type or "media" in task_type or "контент" in assignment or "сторис" in assignment:
        if not any(word in lower for word in ["формат", "текст", "канал", "сценар", "визуал"]):
            problems.append("контентный ответ без формата, текста, канала или сценария")

    if not problems:
        return None

    revision_prompt = (
        "AI Marketing Director проверил ответ и не принимает его как готовый результат. "
        "Нужно довести ответ до состояния согласования с администратором.\n\n"
        "Что исправить:\n- " + "\n- ".join(problems) + "\n\n"
        "Сделай следующий ход самостоятельно: не спрашивай пользователя и не перекладывай ручные действия, "
        "если это можно решить фильтрами, расчётом, уточнением критериев или повторным запросом данных. "
        "Верни: готовый результат, что именно сохранено/подготовлено, риски, что согласовать админу, "
        "и статус: можно передавать директору на согласование или нужна конкретная доработка."
    )
    if revision_bits:
        revision_prompt += "\n\nОсобое указание:\n- " + "\n- ".join(revision_bits)

    return {"needs_revision": True, "problems": problems, "revision_prompt": revision_prompt}


def _evaluate_director_task_closure(reply: str, is_director_handoff: bool) -> Optional[Dict[str, Any]]:
    """Директорский контроль: закрыть задачу или подсветить, что мешает закрытию."""
    if not is_director_handoff:
        return None

    text_value = (reply or "").strip()
    lower = text_value.lower()
    if not text_value:
        return {
            "status": InteractionStatus.PROCESSING.value,
            "reason": "empty_agent_reply",
            "summary": "Агент вернул пустой ответ, задача оставлена в работе для повторного запроса.",
            "needs_user_attention": False,
        }

    user_attention_markers = [
        "нужно согласовать",
        "нужно подтвердить",
        "подтвердить",
        "требует согласования",
        "требует внимания",
        "нужно решение",
        "согласовать с администратором",
        "пока не передавать",
        "нужна доработка",
        "нужно уточнить",
    ]
    blocked_markers = [
        "нет данных",
        "не хватает данных",
        "данных не хватает",
        "не удалось",
        "ошибка",
        "вернула пустой результат",
        "повторить запрос",
    ]
    ready_markers = [
        "можно передавать",
        "готов передать",
        "готово для передачи",
        "передавать директору можно",
        "результат можно передавать",
        "статус для директора",
    ]

    if any(marker in lower for marker in blocked_markers):
        return {
            "status": InteractionStatus.PROCESSING.value,
            "reason": "missing_data_or_retry_required",
            "summary": "Задача оставлена в работе: агент сообщил о нехватке данных или необходимости повторного запроса.",
            "needs_user_attention": False,
        }

    if any(marker in lower for marker in user_attention_markers):
        return {
            "status": InteractionStatus.PENDING_APPROVAL.value,
            "reason": "requires_user_or_director_approval",
            "summary": "Задача требует внимания пользователя/директора: нужно согласовать параметры или доработку.",
            "needs_user_attention": True,
        }

    if any(marker in lower for marker in ready_markers):
        return {
            "status": InteractionStatus.COMPLETED.value,
            "reason": "agent_result_ready_for_director_report",
            "summary": "Агент вернул рабочий результат, его можно использовать в отчете директора. Задача закрыта.",
            "needs_user_attention": False,
        }

    return {
        "status": InteractionStatus.PENDING_APPROVAL.value,
        "reason": "result_requires_director_review",
        "summary": "Агент ответил, но готовность результата не выражена явно. Задача поставлена на проверку директором.",
        "needs_user_attention": True,
    }


def _extract_days_from_text(text: str) -> Optional[int]:
    src = (text or "").lower()
    m_days = re.search(r"(\d{1,4})\s*(дн|дня|дней)\b", src)
    if m_days:
        return int(m_days.group(1))
    m_months = re.search(r"(\d{1,4})\s*(мес|месяц|месяца|месяцев)\b", src)
    if m_months:
        return int(m_months.group(1)) * 30
    m_years = re.search(r"(\d{1,3})\s*(год|года|лет)\b", src)
    if m_years:
        return int(m_years.group(1)) * 365
    return None


def _extract_segment_rules_from_plan(plan_text: str, plan_title: Optional[str] = None) -> Dict[str, Any]:
    combined_text = f"{plan_title or ''}\n{plan_text or ''}"
    src = combined_text.lower()
    brand = _extract_brand_from_text(combined_text)
    city = _extract_city_from_text(combined_text)
    include_filters: List[Dict[str, Any]] = []
    and_filters: List[Dict[str, Any]] = [
        {"field": "is_customer", "operator": "equals", "value": True}
    ]

    if "vip" in src or "вип" in src:
        include_filters.append({"field": "customer_segment", "operator": "contains", "value": "VIP"})

    active_days = None
    active_match = re.search(r"последн[^\n\r]{0,40}(\d{1,4})\s*(дн|дня|дней|мес|месяц|месяца|месяцев|год|года|лет)", src)
    if active_match and ("актив" in src or "покуп" in src):
        active_days = _extract_days_from_text(active_match.group(0))
    if active_days:
        include_filters.append({"field": "last_purchase_date", "operator": "within_last_days", "value": active_days})

    if city:
        and_filters.append({
            "logic": "OR",
            "filters": [
                {"field": "city", "operator": "ilike", "value": city},
                {"field": "preferred_store_name", "operator": "ilike", "value": city},
                {"field": "last_store_name", "operator": "ilike", "value": city},
            ],
        })

    if brand:
        and_filters.append({
            "logic": "OR",
            "filters": [
                {"field": "brand", "operator": "ilike", "value": brand},
                {"field": "product_name", "operator": "ilike", "value": brand},
            ],
        })

    if "без покуп" in src or "лид" in src or brand or city or "рассыл" in src or "сегмент" in src:
        and_filters.append({"field": "total_purchases", "operator": ">=", "value": 1})

    if re.search(r"\b(муж|мужчин|male)\b", src):
        and_filters.append({"field": "gender", "operator": "equals", "value": "male"})
    elif re.search(r"\b(жен|женщин|female)\b", src):
        and_filters.append({"field": "gender", "operator": "equals", "value": "female"})

    inactive_match = re.search(r"неактив[^\n\r]{0,40}(\d{1,4})\s*(дн|дня|дней|мес|месяц|месяца|месяцев|год|года|лет)", src)
    inactive_days = _extract_days_from_text(inactive_match.group(0)) if inactive_match else None
    if inactive_days:
        cutoff = (datetime.utcnow() - timedelta(days=inactive_days)).date().isoformat()
        and_filters.append({"field": "last_purchase_date", "operator": "<=", "value": cutoff})

    if include_filters:
        return {"logic": "AND", "filters": [{"logic": "OR", "filters": include_filters}, *and_filters]}
    return {"logic": "AND", "filters": and_filters}


async def _enrich_rules_with_stores(db: AsyncSession, rules: Dict[str, Any], text: str) -> Dict[str, Any]:
    """
    Scans text for store names and adds them to rules.
    Handles 'secondary' context to map to secondary_store.
    Combines multiple stores with OR logic.
    """
    from app.models.store import Store
    from sqlalchemy import select

    # 1. Fetch all stores (cached check would be better, but simple select is fast enough for now)
    try:
        stores_res = await db.execute(select(Store.name).where(Store.is_active == True))
        all_store_names = [r for r in stores_res.scalars().all() if r]
    except Exception:
        return rules

    found_stores = []
    text_lower = text.lower()

    # Helper to clean store name for loose matching
    # e.g. "ТЦ Меганом" -> "меганом", "Центрум 2" -> "центрум"
    def _clean_store_name(name: str) -> str:
        n = name.lower()
        # Remove common prefixes
        for prefix in ["тц ", "трк ", "трц ", "магазин "]:
            if n.startswith(prefix):
                n = n[len(prefix):]
        # Remove digits and single chars at the end
        n = re.sub(r"\s+\d+$", "", n) # "Centrum 2" -> "Centrum"
        n = re.sub(r"\s+[a-zа-я]$", "", n) # "Store A" -> "Store"
        return n.strip()

    for s_name in all_store_names:
        s_lower = s_name.lower()
        is_match = False

        # 1. Exact/substring match of full name
        if s_lower in text_lower:
            is_match = True
        else:
            # 2. Loose match
            cleaned = _clean_store_name(s_name)
            if len(cleaned) >= 3 and cleaned in text_lower:
                is_match = True

        if is_match:
            # Check context for "secondary"
            # We look for all occurrences of the MATCHED string
            # If loose match, we search for the cleaned string
            search_term = s_lower if s_lower in text_lower else _clean_store_name(s_name)

            start = 0
            while True:
                idx = text_lower.find(search_term, start)
                if idx == -1:
                    break
                # Look at 50 chars before
                context = text_lower[max(0, idx-50):idx]
                is_secondary = "втор" in context or "second" in context or "дополнит" in context
                # Avoid duplicates
                if not any(fs["name"] == s_name and fs["is_secondary"] == is_secondary for fs in found_stores):
                     found_stores.append({"name": s_name, "is_secondary": is_secondary})
                start = idx + len(search_term)

    if not found_stores:
        return rules

    # Fix: Remove "brand" filters that collide with found stores
    # This prevents "corner Meganom" from creating a Brand=Meganom filter which yields 0 results
    found_store_names = {fs["name"].lower() for fs in found_stores}

    # Also create a map of lowercase name -> actual name for correcting the filter values
    store_name_map = {fs["name"].lower(): fs["name"] for fs in found_stores}

    def _clean_brand_filters(filters_list):
        to_remove = []
        for f in filters_list:
            if "logic" in f: # nested group
                _clean_brand_filters(f.get("filters", []))
            elif f.get("field") == "brand":
                val = str(f.get("value") or "").lower()
                # If brand value matches a store name, remove it (assume user meant store)
                for s_name in found_store_names:
                    if s_name in val or val in s_name:
                        to_remove.append(f)
                        break
        for f in to_remove:
            filters_list.remove(f)

    if "filters" in rules:
        _clean_brand_filters(rules["filters"])

    # Construct OR group for stores
    store_filters = []
    for fs in found_stores:
        field = "secondary_store" if fs["is_secondary"] else "preferred_store"
        # Use the actual store name from DB instead of the lowercase search term
        actual_name = store_name_map.get(fs["name"].lower(), fs["name"])
        store_filters.append({
            "field": field,
            "operator": "equals",
            "value": actual_name
        })

    if not store_filters:
        return rules

    # Create the store logic block: (Store A OR Store B OR Secondary C ...)
    store_block = {"logic": "OR", "filters": store_filters}

    # Add to main rules
    # We assume 'rules' is the root AND group from _extract_segment_rules_from_plan
    if rules.get("logic") == "AND":
        # Check if we already have store filters to avoid duplication?
        # _extract_segment_rules_from_plan doesn't extract stores currently, so it's safe.
        if "filters" not in rules:
            rules["filters"] = []
        rules["filters"].append(store_block)
    else:
        # Wrap in AND
        rules = {"logic": "AND", "filters": [rules, store_block]}

    return rules


def _extract_target_audience_size(plan_text: str, plan_title: Optional[str] = None) -> Optional[int]:
    src = f"{plan_title or ''}\n{plan_text or ''}".lower()
    range_match = re.search(
        r"\b(\d{1,5})\s*[-–—]\s*(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)",
        src,
    )
    if range_match:
        try:
            high = int(range_match.group(2))
            if 1 <= high <= 5000:
                return high
        except Exception:
            pass
    patterns = [
        r"(?:цель|целевой\s+размер|размер\s+сегмента)\s*[:—-]?\s*(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)",
        r"из\s+(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)",
        r"(?:нужно|надо|сделать|выбрать|подобрать)\s+(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)",
        r"\b(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)\b",
        r"на\s+(\d{1,5})\s*(?:покупател|клиент|получател|контакт|человек)"
    ]
    for p in patterns:
        m = re.search(p, src)
        if not m:
            continue
        try:
            n = int(m.group(1))
            if 1 <= n <= 5000:
                return n
        except Exception:
            pass
    return None


async def _calc_count(db: AsyncSession, rules: Dict[str, Any]) -> int:
    from sqlalchemy import select, func
    from app.api.customer_segmentation import _build_select_for_rules
    base_stmt, _ = _build_select_for_rules(rules)
    subq = base_stmt.subquery()
    res = await db.execute(select(func.count()).select_from(subq))
    return int(res.scalar() or 0)


async def _refresh_bound_segment_context(
    db: AsyncSession,
    task: AgentInteractionTask,
    selected_segment_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Load the task-bound CRM segment and make task context match the DB source of truth."""
    ctx = dict(task.task_context or {})
    task_uuid = task.id
    seg_id_raw = selected_segment_id or ctx.get("segment_id")
    if not seg_id_raw:
        return None

    try:
        seg_uuid = UUID(str(seg_id_raw))
    except Exception:
        return None

    from app.models.customer_segment import CustomerSegment

    seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
    seg = seg_row.scalar_one_or_none()
    if not seg or not bool(getattr(seg, "is_active", False)):
        return None

    rules = seg.rules if isinstance(seg.rules, dict) else {}
    count_val = int(seg.customer_count or 0)
    if rules:
        try:
            count_val = await _save_segment_membership(db, seg.id, rules, assigned_by="ai", confidence_score=0.92)
        except Exception:
            logger.warning("Failed to refresh bound CRM segment membership", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            task_row = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_uuid))
            task = task_row.scalar_one_or_none() or task
            seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
            seg = seg_row.scalar_one_or_none()
            if not seg:
                return None
            rules = seg.rules if isinstance(seg.rules, dict) else {}
            count_val = int(seg.customer_count or 0)

    edit_path = ctx.get("segment_edit_path") or "/admin/customers/segments"
    for key in SEGMENT_CONTEXT_STALE_KEYS:
        ctx.pop(key, None)
    ctx["segment_id"] = str(seg.id)
    ctx["segment_name"] = seg.name
    ctx["segment_rules"] = rules
    ctx["segment_customer_count"] = count_val
    ctx["segment_edit_path"] = edit_path
    ctx["selected_segment_locked"] = True
    task.task_context = ctx
    seg.customer_count = count_val
    seg.updated_at = datetime.utcnow()
    db.add(task)
    db.add(seg)
    await db.commit()
    await db.refresh(task)
    await db.refresh(seg)
    return {
        "id": str(seg.id),
        "name": seg.name,
        "count": count_val,
        "rules": rules,
        "edit_path": edit_path,
    }


def _should_use_recommendation_expansion(text: str) -> bool:
    src = (text or "").lower()
    return any(
        marker in src
        for marker in [
            "рекоменд", "похож", "похожие", "стилистичес", "сочетан", "компаньон",
            "средний чек", "высокий чек", "новых", "новые", "привлечь", "которым тоже",
            "может понрав", "интерес к сереб", "крупн", "statement",
        ]
    )


async def _build_recommended_crm_segment_rules(
    db: AsyncSession,
    source_text: str,
    target: Optional[int],
    fallback_rules: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], int, Dict[str, Any]]]:
    """Build a real ranked CRM audience from DB signals when the task asks for similar buyers."""
    if not target or target <= 0 or not _should_use_recommendation_expansion(source_text):
        return None

    city = _extract_city_from_text(source_text) or "Симферополь"
    brand = _extract_brand_from_text(source_text) or "UNOde50"
    source_l = (source_text or "").lower()
    store_name = "Центрум" if ("центрум" in source_l or "симферопол" in source_l) else ""
    limit = max(1, min(int(target), 5000))

    # This is the CRM-side recommender: rank customers by exact brand history,
    # stylistic purchase signals, monetary value, frequency and recency.
    rows = await db.execute(
        sql_text(
            """
            WITH customer_features AS (
                SELECT
                    u.id,
                    max(CASE WHEN ph.brand ILIKE :brand_like OR ph.product_name ILIKE :brand_like THEN 1 ELSE 0 END) AS brand_hit,
                    max(CASE
                        WHEN ph.product_name ILIKE '%серебр%'
                          OR ph.category ILIKE '%серебр%'
                          OR ph.product_name ILIKE '%statement%'
                          OR ph.product_name ILIKE '%крупн%'
                          OR ph.product_name ILIKE '%кольц%'
                          OR ph.product_name ILIKE '%браслет%'
                          OR ph.product_name ILIKE '%чокер%'
                          OR ph.product_name ILIKE '%серьг%'
                        THEN 1 ELSE 0
                    END) AS style_hit,
                    max(CASE WHEN u.average_check >= 1500000 OR u.total_spent >= 5000000 OR u.customer_segment ILIKE '%VIP%' THEN 1 ELSE 0 END) AS value_hit,
                    max(CASE WHEN u.last_purchase_date >= now() - interval '180 days' THEN 1 ELSE 0 END) AS active_hit,
                    max(CASE
                        WHEN u.city ILIKE :city_like
                          OR u.preferred_store_name ILIKE :city_like
                          OR u.preferred_store_name ILIKE :store_like
                          OR ph.store_id_1c IN (
                              SELECT external_id FROM stores
                              WHERE external_id IS NOT NULL
                                AND (name ILIKE :store_like OR name ILIKE :city_like)
                          )
                        THEN 1 ELSE 0
                    END) AS location_hit,
                    count(ph.id) AS line_count,
                    coalesce(u.total_purchases, 0) AS total_purchases,
                    coalesce(u.total_spent, 0) AS total_spent,
                    coalesce(u.average_check, 0) AS average_check,
                    u.last_purchase_date
                FROM users u
                LEFT JOIN purchase_history ph ON ph.user_id = u.id
                WHERE u.is_customer = true
                GROUP BY u.id
            )
            SELECT id
            FROM customer_features
            WHERE location_hit = 1
              AND total_purchases >= 1
              AND (brand_hit = 1 OR style_hit = 1 OR value_hit = 1)
            ORDER BY
                (brand_hit * 100
                 + style_hit * 42
                 + value_hit * 32
                 + active_hit * 18
                 + LEAST(total_purchases, 10) * 2
                 + LEAST(total_spent / 1000000.0, 20)
                 + LEAST(average_check / 1000000.0, 10)) DESC,
                last_purchase_date DESC NULLS LAST,
                total_spent DESC,
                id
            LIMIT :limit
            """
        ),
        {
            "brand_like": f"%{brand}%",
            "city_like": f"%{city}%",
            "store_like": f"%{store_name or city}%",
            "limit": limit,
        },
    )
    user_ids = [str(row[0]) for row in rows.all() if row and row[0]]
    if not user_ids:
        return None

    rules = {"logic": "AND", "filters": [{"field": "id", "operator": "in", "value": user_ids}]}
    meta = {
        "ranking": "crm_recommendation_expansion",
        "brand": brand,
        "city": city,
        "store": store_name or city,
        "target": limit,
        "source_rules": fallback_rules,
        "signals": [
            "brand_purchase_history",
            "stylistic_purchase_similarity",
            "average_check_ltv_vip",
            "recent_activity",
            "preferred_or_purchase_store",
        ],
    }
    return rules, len(user_ids), meta


async def _save_segment_membership(
    db: AsyncSession,
    segment_id: UUID,
    rules: Dict[str, Any],
    assigned_by: str = "ai",
    confidence_score: Optional[float] = None,
) -> int:
    from app.api.customer_segmentation import materialize_segment_members

    return await materialize_segment_members(
        db,
        segment_id,
        rules,
        assigned_by=assigned_by,
        confidence_score=confidence_score,
    )


def _get_filter(rules: Dict[str, Any], field: str):
    for f in rules.get("filters", []):
        if isinstance(f, dict) and f.get("field") == field:
            return f
        if isinstance(f, dict) and "logic" in f:
            for sf in f.get("filters", []):
                if sf.get("field") == field:
                    return sf
    return None


def _set_or_replace_filter(rules: Dict[str, Any], new_filter: Dict[str, Any]) -> Dict[str, Any]:
    filters = list(rules.get("filters", []))
    replaced = False
    for i, f in enumerate(filters):
        if isinstance(f, dict) and f.get("field") == new_filter.get("field"):
            filters[i] = new_filter
            replaced = True
            break
    if not replaced:
        filters.append(new_filter)
    rules["filters"] = filters
    return rules


async def _tune_rules_towards_target(db: AsyncSession, rules: Dict[str, Any], target: int, max_iters: int = 5) -> Dict[str, Any]:
    try:
        count = await _calc_count(db, rules)
    except Exception:
        return rules
    if target <= 0:
        return rules
    for _ in range(max_iters):
        if count == 0:
            # Расслабляем
            # 1. Gender
            g = _get_filter(rules, "gender")
            if g:
                rules["filters"] = [f for f in rules.get("filters", []) if f is not g]

            # 2. Last Purchase Date
            lp = _get_filter(rules, "last_purchase_date")
            if lp and lp.get("operator") == "within_last_days":
                lp["value"] = min(int(lp.get("value") or 0) * 2 or 60, 730)
                rules = _set_or_replace_filter(rules, lp)
            else:
                # If not present, don't force it unless we really need to, but here we are relaxing...
                # Actually if it's 0, maybe we should REMOVE strict date filters if they exist?
                # But let's stick to expanding range first.
                pass

            # 3. City (New: remove city if still 0)
            # We do this in a later iteration or if previous didn't help?
            # Let's do it if we are desperate (e.g. 2nd iteration)
            c = _get_filter(rules, "city")
            if c:
                 # Only remove city if we already tried relaxing others
                 rules["filters"] = [f for f in rules.get("filters", []) if f is not c]

        elif count > target:
            # Ужесточаем
            lp = _get_filter(rules, "last_purchase_date")
            if not lp:
                rules = _set_or_replace_filter(rules, {"field": "last_purchase_date", "operator": "within_last_days", "value": 365})
            else:
                if lp.get("operator") == "within_last_days":
                    v = int(lp.get("value") or 365)
                    lp["value"] = max(30, v // 2)
                    rules = _set_or_replace_filter(rules, lp)
            tp = _get_filter(rules, "total_purchases")
            if not tp:
                rules = _set_or_replace_filter(rules, {"field": "total_purchases", "operator": ">=", "value": 1})
            else:
                if tp.get("operator") == ">=":
                    tp["value"] = int(tp.get("value") or 0) + 1
                    rules = _set_or_replace_filter(rules, tp)
        else:  # count < target
            # Расслабляем
            tp = _get_filter(rules, "total_purchases")
            if tp and tp.get("operator") == ">=" and int(tp.get("value") or 0) > 0:
                tp["value"] = max(0, int(tp.get("value")) - 1)
                rules = _set_or_replace_filter(rules, tp)
            lp = _get_filter(rules, "last_purchase_date")
            if lp and lp.get("operator") == "within_last_days":
                lp["value"] = min(730, int(lp.get("value") or 0) + 90)
                rules = _set_or_replace_filter(rules, lp)
        try:
            new_count = await _calc_count(db, rules)
        except Exception:
            break
        # Останавливаемся, если приблизились на ±10%
        if abs(new_count - target) <= max(1, int(target * 0.1)):
            break
        count = new_count
    return rules

@router.post("/tasks/{task_id}/mass-mailing/prepare", response_model=MassMailingPrepareResponse)
async def prepare_mass_mailing_actions(
    task_id: UUID,
    body: MassMailingPrepareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    from app.models.customer_segment import CustomerSegment
    from app.models.user import User as UserModel
    from sqlalchemy import func
    from app.api.customer_segmentation import _build_select_for_rules

    task_ctx = dict(task.task_context or {})
    bound_seg_id = None
    try:
        raw = task_ctx.get("segment_id")
        if raw:
            bound_seg_id = UUID(str(raw))
    except Exception:
        bound_seg_id = None

    segment_source_text = "\n".join([
        body.plan_title or "",
        body.plan_text or "",
        body.brand or "",
        body.event_type or "",
    ])
    segment_meta = _extract_segment_business_meta(segment_source_text)
    segment_name = segment_meta.get("name") or _make_segment_name(task_id, body.plan_title)
    if not bound_seg_id:
        existing = await db.execute(select(CustomerSegment).where(CustomerSegment.name == segment_name))
        if existing.scalar_one_or_none():
            segment_name = f"{segment_name}_{uuid.uuid4().hex[:6]}"
            segment_name = segment_name[:100]

    # Pre-fetch segment to check if it is manual
    seg = None
    if bound_seg_id:
        seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == bound_seg_id))
        seg = seg_row.scalar_one_or_none()
    seg_was_auto_generated = bool(getattr(seg, "is_auto_generated", True)) if seg else True
    metadata = body.metadata or {}
    force_resegment = bool(metadata.get("force_resegment") or metadata.get("recalculate_segment"))

    if seg is not None and bool(getattr(seg, "is_active", False)) and not force_resegment:
        segment_rules = seg.rules if isinstance(seg.rules, dict) else {}
        if segment_rules:
            customer_count = await _save_segment_membership(db, seg.id, segment_rules, assigned_by="ai", confidence_score=0.92)
            seg.customer_count = customer_count
            seg.updated_at = datetime.utcnow()
        else:
            customer_count = int(seg.customer_count or 0)

        task_ctx["segment_id"] = str(seg.id)
        task_ctx["segment_name"] = seg.name
        task_ctx["segment_rules"] = segment_rules
        task_ctx["segment_customer_count"] = customer_count
        task_ctx["segment_edit_path"] = "/admin/customers/segments"
        task_ctx["selected_segment_locked"] = True
        task.task_context = task_ctx
        db.add(
            AgentInteractionLog(
                task_id=task.id,
                agent_name="communication-agent",
                event_type="mass_mailing_prepare",
                event_data={
                    "segment_id": str(seg.id),
                    "segment_name": seg.name,
                    "customer_count": customer_count,
                    "source": "bound_segment_refresh",
                },
                message=f"Использован уже привязанный сегмент без пересборки: {seg.name} ({customer_count})",
            )
        )
        await db.commit()
        await db.refresh(seg)

        event_type = body.event_type or _derive_mass_event_type(body.plan_title, body.plan_text)
        limit = int(body.message_count or _derive_message_count(body.plan_text, fallback=100))
        brand = body.brand or "GLAME"
        suggested = MassMailingSuggestedRequest(
            brand=brand,
            limit=limit,
            auto_detect_store=True,
            event={
                "type": event_type,
                "brand": brand,
                "metadata": {k: v for k, v in {"plan_title": body.plan_title, **metadata}.items() if v is not None},
            },
            search_criteria={"segment_id": str(seg.id)},
        )
        report = "\n".join(
            [
                "Отчёт по плану массовой генерации",
                "",
                f"- Сегмент: {seg.name} ({customer_count} покупателей в базе)",
                "- Использован уже привязанный к задаче сегмент; устаревший текст ответа не пересобирал фильтр.",
                f"- Тип события: {event_type}",
                f"- Количество сообщений: {limit}",
            ]
        )
        return MassMailingPrepareResponse(
            report=report,
            segment=MassMailingSegmentInfo(id=str(seg.id), name=seg.name, customer_count=customer_count),
            suggested_request=suggested,
        )

    # Determine rules: use existing for manual segments, extract from text for auto/new
    if seg and not seg_was_auto_generated:
        segment_rules = seg.rules
        # Recalculate count to be sure
        customer_count = await _calc_count(db, segment_rules)
    else:
        segment_rules = _extract_segment_rules_from_plan(body.plan_text, body.plan_title)
        # Дополняем правила строгим фильтром «последний магазин» по названиям, если они явно упомянуты
        try:
            from app.models.store import Store
            from sqlalchemy import select as _sel
            wanted_store_names: List[str] = []
            src_l = f"{body.plan_title or ''}\n{body.plan_text or ''}".lower()
            if "меганом" in src_l:
                wanted_store_names.append("меганом")
            if "центр" in src_l or "центрум" in src_l:
                # «Центрум» и варианты
                wanted_store_names.append("центрум")
            if wanted_store_names:
                # Fix: Clean up brand filters that match found stores
                def _clean_brand_filters(filters_list):
                    to_remove = []
                    for f in filters_list:
                        if "logic" in f:
                            _clean_brand_filters(f.get("filters", []))
                        elif f.get("field") == "brand":
                            val = str(f.get("value") or "").lower()
                            for s_name in wanted_store_names:
                                if s_name.lower() in val or val in s_name.lower():
                                    to_remove.append(f)
                                    break
                    for f in to_remove:
                        filters_list.remove(f)

                if "filters" in segment_rules:
                    _clean_brand_filters(segment_rules["filters"])

                q = _sel(Store.external_id).where(Store.external_id.isnot(None))
                # Фильтр по названию
                from sqlalchemy import or_
                name_clauses = []
                for n in wanted_store_names:
                    name_clauses.append(Store.name.ilike(f"%{n}%"))
                if name_clauses:
                    q = q.where(or_(*name_clauses))
                # Re-fetch rows because result proxy might be closed/consumed
                rows = await db.execute(q)
                db_store_map = {}
                for r in rows.all():
                    if r and r[0]:
                        db_store_map[r[0].lower()] = r[0]

                final_store_names = []
                for w in wanted_store_names:
                    w_lower = w.lower()
                    # Try exact match first
                    if w_lower in db_store_map:
                        final_store_names.append(db_store_map[w_lower])
                        continue
                    # Try partial match
                    matched = False
                    for db_lower, db_real in db_store_map.items():
                        if w_lower in db_lower or db_lower in w_lower:
                            final_store_names.append(db_real)
                            matched = True
                            break
                    if not matched:
                        final_store_names.append(w.title())

                if final_store_names:
                    segment_rules = _set_or_replace_filter(
                        segment_rules,
                        {"field": "preferred_store", "operator": "in", "value": final_store_names}
                    )
        except Exception:
            # Молча пропускаем, если не получилось обогатить правила
            pass
        target_size = _extract_target_audience_size(body.plan_text, body.plan_title)
        try:
            # Базовый расчёт
            base_stmt, _ = _build_select_for_rules(segment_rules)
            subq = base_stmt.subquery()
            count_result = await db.execute(select(func.count()).select_from(subq))
            customer_count = int(count_result.scalar() or 0)
            # Пытаемся приблизить правила к целевому размеру
            if target_size:
                tuned_rules = await _tune_rules_towards_target(db, dict(segment_rules), target_size, max_iters=5)
                if tuned_rules != segment_rules:
                    segment_rules = tuned_rules
                    customer_count = await _calc_count(db, segment_rules)
            recommended_segment = await _build_recommended_crm_segment_rules(db, segment_source_text, target_size, segment_rules)
            if recommended_segment:
                segment_rules, customer_count, recommendation_meta = recommended_segment
                segment_meta["recommendation_expansion"] = recommendation_meta
            # Если всё ещё сильно больше целевого — жёсткий top-N как страховка
            elif target_size and customer_count > target_size:
                fresh_base_stmt, _ = _build_select_for_rules(segment_rules)
                subq_ids = fresh_base_stmt.subquery()
                top_ids_stmt = (
                    select(UserModel.id)
                    .where(UserModel.id.in_(select(subq_ids.c.id)))
                    .order_by(
                        UserModel.last_purchase_date.desc().nullslast(),
                        UserModel.total_purchases.desc(),
                        UserModel.total_spent.desc(),
                    )
                    .limit(target_size)
                )
                top_ids_result = await db.execute(top_ids_stmt)
                top_ids = [str(uid) for uid in top_ids_result.scalars().all()]
                if top_ids:
                    segment_rules = {"logic": "AND", "filters": [{"field": "id", "operator": "in", "value": top_ids}]}
                    customer_count = len(top_ids)
        except Exception:
            # Сбрасываем транзакцию после SQL-ошибки перед резервным подсчётом
            logger.warning("Failed to calculate customer segment for mass mailing prepare", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            # rollback expires ORM instances in async sessions; reload objects before touching attributes.
            task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
            task = task_result.scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=404, detail="Задача не найдена")
            if bound_seg_id:
                seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == bound_seg_id))
                seg = seg_row.scalar_one_or_none()
                seg_was_auto_generated = bool(getattr(seg, "is_auto_generated", True)) if seg else True
            total_customers_result = await db.execute(select(func.count(UserModel.id)).where(UserModel.is_customer == True))
            customer_count = int(total_customers_result.scalar() or 0)
            segment_rules = {"logic": "AND", "filters": [{"field": "is_customer", "operator": "equals", "value": True}]}

    # Update or Create segment
    if seg is not None and bool(getattr(seg, "is_active", False)):
        # Only update rules if it's auto-generated.
        # For manual segments, we only update the count (just in case) but NOT the rules.
        if seg_was_auto_generated:
            seg.name = _dedupe_segment_name(segment_name, str(seg.id))
            seg.rules = segment_rules
            seg.description = _make_ai_segment_description(segment_meta, segment_source_text)

        seg.customer_count = customer_count
        seg.updated_at = datetime.utcnow()
    else:
        seg = CustomerSegment(
            id=uuid.uuid4(),
            name=_dedupe_segment_name(segment_name, str(task_id)),
            description=_make_ai_segment_description(segment_meta, segment_source_text),
            rules=segment_rules,
            customer_count=customer_count,
            is_auto_generated=True,
            is_active=True,
        )
        db.add(seg)
        await db.flush()
    customer_count = await _save_segment_membership(db, seg.id, segment_rules, assigned_by="ai", confidence_score=0.92)
    seg.customer_count = customer_count
    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="communication-agent",
            event_type="mass_mailing_prepare",
            event_data={"segment_id": str(seg.id), "segment_name": seg.name, "rules": segment_rules, "meta": segment_meta},
            message=f"Создан сегмент '{seg.name}'",
        )
    )
    # Привязываем сегмент к задаче, чтобы он не пропадал после обновления
    task_ctx["segment_id"] = str(seg.id)
    task_ctx["segment_name"] = seg.name
    task_ctx["segment_rules"] = segment_rules
    task_ctx["segment_meta"] = segment_meta
    task_ctx["segment_customer_count"] = customer_count
    task_ctx["segment_edit_path"] = segment_meta.get("edit_path") or "/admin/customers/segments"
    task.task_context = task_ctx
    await db.commit()
    await db.refresh(seg)

    event_type = body.event_type or _derive_mass_event_type(body.plan_title, body.plan_text)
    limit = int(body.message_count or _derive_message_count(body.plan_text, fallback=100))
    brand = body.brand or "GLAME"
    meta = {
        "plan_title": body.plan_title,
        "channel": "sms" if ("sms" in (body.plan_text or "").lower() or "смс" in (body.plan_text or "").lower()) else None,
        **(body.metadata or {}),
    }
    meta = {k: v for k, v in meta.items() if v is not None}

    suggested = MassMailingSuggestedRequest(
        brand=brand,
        limit=limit,
        auto_detect_store=True,
        event={
            "type": event_type,
            "brand": brand,
            "metadata": meta,
        },
        search_criteria={"segment_id": str(seg.id)},
    )

    report_lines = [
        "Отчёт по плану массовой генерации",
        "",
        f"- Сегмент: {seg.name} ({customer_count} покупателей в базе)",
        f"- Тип события: {event_type}",
        f"- Количество сообщений: {limit}",
        "- Отправка сообщений не выполняется автоматически (только ручная рассылка).",
        "- Результат сохранится в историю генераций и будет доступен в интерфейсе массовой генерации.",
    ]
    report = "\n".join(report_lines)

    return MassMailingPrepareResponse(
        report=report,
        segment=MassMailingSegmentInfo(id=str(seg.id), name=seg.name, customer_count=customer_count),
        suggested_request=suggested,
    )


@router.get("/tasks/{task_id}/segment", response_model=MassMailingSegmentInfo | Dict[str, Any])
async def get_task_segment(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    res = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    ctx = task.task_context or {}
    seg_id = ctx.get("segment_id")
    if not seg_id:
        return {"message": "segment_not_bound"}
    bound_info = await _refresh_bound_segment_context(db, task)
    if not bound_info:
        return {"message": "segment_not_found", "segment_id": str(seg_id)}
    return MassMailingSegmentInfo(
        id=bound_info["id"],
        name=bound_info["name"],
        customer_count=int(bound_info["count"] or 0),
    )


@router.put("/tasks/{task_id}/segment", response_model=MassMailingSegmentInfo)
async def bind_task_segment(
    task_id: UUID,
    body: BindSegmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Привязка существующего сегмента к задаче"""
    from app.models.customer_segment import CustomerSegment

    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    try:
        seg_uuid = UUID(body.segment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный ID сегмента")

    seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
    seg = seg_row.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Сегмент не найден")

    rules = seg.rules if isinstance(seg.rules, dict) else {}
    customer_count = int(seg.customer_count or 0)
    if rules:
        customer_count = await _save_segment_membership(db, seg.id, rules, assigned_by="ai", confidence_score=0.92)
        seg.customer_count = customer_count
        seg.updated_at = datetime.utcnow()

    ctx = dict(task.task_context or {})
    ctx["segment_id"] = str(seg.id)
    ctx["segment_name"] = seg.name
    ctx["segment_rules"] = rules
    ctx["segment_customer_count"] = customer_count
    ctx["segment_edit_path"] = ctx.get("segment_edit_path") or "/admin/customers/segments"
    ctx["selected_segment_locked"] = True
    task.task_context = ctx
    db.add(task)
    db.add(seg)

    # Логируем событие
    db.add(AgentInteractionLog(
        task_id=task.id,
        agent_name="user",
        event_type="segment_bound",
        event_data={"segment_id": str(seg.id), "segment_name": seg.name, "customer_count": customer_count},
        message=f"Привязан выбранный сегмент '{seg.name}' ({customer_count})"
    ))

    await db.commit()
    await db.refresh(seg)

    return MassMailingSegmentInfo(id=str(seg.id), name=seg.name, customer_count=customer_count)


@router.post("/tasks/{task_id}/mass-mailing/run", response_model=MassMailingRunResponse)
async def run_mass_mailing_actions(
    task_id: UUID,
    body: MassMailingRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    task_result = await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    from app.models.customer_segment import CustomerSegment

    seg_id_raw = body.segment_id or (task.task_context or {}).get("segment_id")
    if not seg_id_raw:
        raise HTTPException(status_code=400, detail="segment_id не указан и не привязан к задаче")
    try:
        seg_uuid = UUID(str(seg_id_raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный формат segment_id (UUID).")

    seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid))
    seg = seg_row.scalar_one_or_none()
    if not seg or not seg.is_active:
        raise HTTPException(status_code=404, detail="Сегмент не найден или не активен")

    from app.api.communication import BatchGenerateRequest, SearchCriteria, EventData, batch_generate_messages_async

    preview_limit = min(int(body.message_count or 25), int(os.getenv("COMMUNICATION_BATCH_MAX_LLM_MESSAGES", "500")))
    req = BatchGenerateRequest(
        event=EventData(
            type=body.event_type,
            brand=body.brand or "GLAME",
            store=None,
            metadata=body.metadata or {},
        ),
        limit=preview_limit,
        auto_detect_store=body.auto_detect_store,
        search_criteria=SearchCriteria(segment_id=str(seg.id)),
    )
    started = await batch_generate_messages_async(req)

    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="communication-agent",
            event_type="mass_mailing_run",
            event_data={"segment_id": str(seg.id), "generation_id": started.generation_id, "requested_count": body.message_count, "preview_limit": preview_limit},
            message=f"Запущена preview-генерация сообщений (generation_id={started.generation_id}, limit={preview_limit})",
        )
    )
    await db.commit()

    report_lines = [
        "Запуск массовой генерации",
        "",
        f"- Сегмент: {seg.name}",
        f"- Тип события: {body.event_type}",
        f"- Preview-сообщений к генерации: {preview_limit}",
        f"- Запрошено пользователем: {body.message_count}",
        "- Полная генерация по всему сегменту требует отдельного подтверждения и увеличения лимита.",
        f"- generation_id: {started.generation_id}",
    ]
    report = "\n".join(report_lines)

    return MassMailingRunResponse(
        report=report,
        segment=MassMailingSegmentInfo(id=str(seg.id), name=seg.name, customer_count=int(seg.customer_count or 0)),
        generation_id=started.generation_id,
        events_url=started.events_url,
    )
