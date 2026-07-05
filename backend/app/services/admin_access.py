from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_access import AdminRoleAccess


ROLE_ADMIN = "admin"
ROLE_MARKETER = "marketer"
ROLE_MANAGER = "manager"
ROLE_SELLER = "seller"

ROLE_ALIASES = {
    "ai_marketer": ROLE_MARKETER,
    "content_manager": ROLE_MANAGER,
    "administrator": ROLE_ADMIN,
    "owner": ROLE_ADMIN,
    "user": "customer",
}


@dataclass(frozen=True)
class AdminSection:
    id: str
    name: str
    href: str
    group: str


ADMIN_SECTIONS: tuple[AdminSection, ...] = (
    AdminSection("customer_stylist", "Связь со стилистом", "/admin/live-stylist", "AI инструменты"),
    AdminSection("sellers", "Продавцы", "/profile/sellers", "Аккаунт"),
    AdminSection("content_generator", "Генератор контента", "/content-generator", "AI инструменты"),
    AdminSection("content_agent", "AI Контент-агент", "/content-agent", "AI инструменты"),
    AdminSection("ai_marketer", "AI Маркетолог", "/ai-marketer", "AI инструменты"),
    AdminSection("ai_marketer_tasks", "Задачи маркетолога", "/ai-marketer/tasks", "AI инструменты"),
    AdminSection("consultant_training", "AI Тренер консультантов", "/admin/consultant-training", "AI инструменты"),
    AdminSection("seller_training", "Обучение GLAME", "/profile/training", "Аккаунт"),
    AdminSection("batch_messages", "Массовая генерация", "/admin/batch-messages", "AI инструменты"),
    AdminSection("knowledge_base", "База знаний", "/knowledge-base", "Управление"),
    AdminSection("products", "Каталог товаров", "/products", "Управление"),
    AdminSection("looks", "Образы", "/looks", "Управление"),
    AdminSection("customers", "Покупатели", "/admin/customers", "Управление"),
    AdminSection("referrals_admin", "Партнеры", "/admin/referrals", "Управление"),
    AdminSection("analytics", "Аналитика", "/analytics", "Аналитика"),
    AdminSection("product_analytics", "Аналитика товара", "/product-analytics", "Аналитика"),
    AdminSection("inventory_control", "Контроль запасов", "/inventory-control", "Операции"),
    AdminSection("inventory_tasks", "Задачи ИИ по запасам", "/inventory-control/tasks", "Операции"),
    AdminSection("settings", "Настройки", "/settings", "Система"),
    AdminSection("admin_cron", "CRON регламенты", "/admin/cron", "Система"),
    AdminSection("app_admin", "Администрирование приложения", "/admin/app", "Система"),
    AdminSection("shipping_admin", "Администрирование доставки", "/admin/shipping", "Система"),
    AdminSection("inventory_admin", "Админка запасов", "/admin/inventory-control", "Система"),
    AdminSection("system_prompts", "Системные промпты", "/admin/prompts", "Система"),
    AdminSection("roles_access", "Роли и доступы", "/admin/roles", "Система"),
)

ALL_SECTION_IDS = tuple(section.id for section in ADMIN_SECTIONS)

ROLE_LABELS = {
    ROLE_ADMIN: "Админ",
    ROLE_MARKETER: "Маркетолог",
    ROLE_MANAGER: "Управляющий",
    ROLE_SELLER: "Продавец",
}

DEFAULT_ROLE_SECTIONS: dict[str, list[str]] = {
    ROLE_ADMIN: list(ALL_SECTION_IDS),
    ROLE_MARKETER: [
        "content_generator",
        "content_agent",
        "ai_marketer",
        "ai_marketer_tasks",
        "consultant_training",
        "batch_messages",
        "customers",
        "analytics",
        "product_analytics",
        "admin_cron",
        "app_admin",
    ],
    ROLE_MANAGER: [
        "sellers",
        "consultant_training",
        "seller_training",
        "knowledge_base",
        "products",
        "looks",
        "customers",
        "referrals_admin",
        "analytics",
        "product_analytics",
        "inventory_control",
        "inventory_tasks",
        "app_admin",
        "shipping_admin",
        "inventory_admin",
    ],
    ROLE_SELLER: [
        "customer_stylist",
        "seller_training",
        "products",
        "looks",
        "customers",
    ],
}

STAFF_ROLES = tuple(ROLE_LABELS.keys())


def normalize_role(role: str | None) -> str | None:
    value = (role or "").strip().lower()
    if not value:
        return None
    return ROLE_ALIASES.get(value, value)


def clean_section_ids(section_ids: Iterable[str] | None) -> list[str]:
    allowed = set(ALL_SECTION_IDS)
    result: list[str] = []
    for section_id in section_ids or []:
        value = str(section_id).strip()
        if value in allowed and value not in result:
            result.append(value)
    return result


def default_sections_for_role(role: str | None) -> list[str]:
    normalized = normalize_role(role)
    if normalized == ROLE_ADMIN:
        return list(ALL_SECTION_IDS)
    return list(DEFAULT_ROLE_SECTIONS.get(normalized or "", []))


async def ensure_default_role_access(db: AsyncSession) -> None:
    changed = False
    for role_key, label in ROLE_LABELS.items():
        result = await db.execute(select(AdminRoleAccess).where(AdminRoleAccess.role_key == role_key))
        access = result.scalar_one_or_none()
        if access is None:
            db.add(
                AdminRoleAccess(
                    role_key=role_key,
                    role_label=label,
                    section_ids=DEFAULT_ROLE_SECTIONS[role_key],
                    is_system=True,
                )
            )
            changed = True
    if changed:
        await db.commit()


async def get_allowed_sections(db: AsyncSession, role: str | None) -> list[str]:
    normalized = normalize_role(role)
    if normalized == ROLE_ADMIN:
        return list(ALL_SECTION_IDS)
    if not normalized:
        return []
    result = await db.execute(select(AdminRoleAccess).where(AdminRoleAccess.role_key == normalized))
    access = result.scalar_one_or_none()
    if access:
        return clean_section_ids(access.section_ids)
    return default_sections_for_role(normalized)
