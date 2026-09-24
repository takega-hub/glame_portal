"""Adaptive daily sales plan for the personal KPI screen.

The calculation intentionally keeps the plan explainable: a working monthly
target is distributed across all remaining days by weekday, calendar and
front-loaded pacing weights. Weekday factors learn from 90/120/180-day sales
windows and are blended with GLAME's approved starting coefficients.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.seller_kpi_service import (
    KPI_ELIGIBLE_PRODUCT_SQL,
    SELLER_KEY_EXPR,
    SellerKPIService,
)


# Python weekday: Monday=0 … Sunday=6.
BASE_WEEKDAY_COEFFICIENTS = (0.87, 0.76, 1.14, 1.07, 0.95, 1.13, 1.08)


class AdaptiveDailyPlanService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.kpi = SellerKPIService(db)

    @staticmethod
    def _round_money(value: float) -> int:
        return max(0, int(round(value / 1000.0) * 1000))

    @staticmethod
    def _calendar_coefficient(day: date) -> float:
        if day.day in {15, 25}:
            return 1.08
        if 25 <= day.day <= 28:
            return 1.03
        return 1.0

    @staticmethod
    def _pacing_coefficient(day: date, today: date, month_end: date) -> float:
        total = max((month_end - today).days, 1)
        progress = max(0.0, min(1.0, (day - today).days / total))
        return 1.10 - 0.18 * progress

    async def _history_daily_sales(self, *, seller_id: str, store_id: Optional[str], today: date) -> list[dict]:
        start = today - timedelta(days=180)
        params: Dict[str, Any] = {"start": start, "end": today, "seller_id": seller_id}
        store_where = ""
        if store_id:
            store_where = "AND sr.store_id=:store_id"
            params["store_id"] = store_id
        result = await self.db.execute(text(f"""
            SELECT sr.sale_date::date AS sale_date,
                   SUM(CASE WHEN {KPI_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END)::float AS net_revenue
            FROM sales_records sr
            LEFT JOIN products p ON p.external_id=sr.product_id
            WHERE sr.sale_date >= :start AND sr.sale_date < :end
              AND {SELLER_KEY_EXPR}=:seller_id
              {store_where}
            GROUP BY sr.sale_date::date
            ORDER BY sale_date
        """), params)
        return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def _learn_weekday_coefficients(history: list[dict]) -> tuple[list[float], dict]:
        # Blend three windows to prevent a single recent spike from changing a plan.
        factors: list[float] = []
        evidence: dict[str, Any] = {"windows": {}}
        if not history:
            return list(BASE_WEEKDAY_COEFFICIENTS), evidence
        latest = max(row["sale_date"] for row in history)
        for window, weight in ((90, 0.5), (120, 0.3), (180, 0.2)):
            rows = [row for row in history if row["sale_date"] >= latest - timedelta(days=window - 1)]
            values = [float(row.get("net_revenue") or 0) for row in rows]
            mean = sum(values) / len(values) if values else 0
            weekday_means = []
            for weekday in range(7):
                weekday_values = [float(row.get("net_revenue") or 0) for row in rows if row["sale_date"].weekday() == weekday]
                weekday_means.append((sum(weekday_values) / len(weekday_values) / mean) if weekday_values and mean else None)
            evidence["windows"][str(window)] = {"days": len(rows), "mean": round(mean, 2)}
            factors.append((weight, weekday_means))
        learned: list[float] = []
        for weekday, base in enumerate(BASE_WEEKDAY_COEFFICIENTS):
            weighted = [(weight, values[weekday]) for weight, values in factors if values[weekday] is not None]
            observed = sum(weight * value for weight, value in weighted) / sum(weight for weight, _ in weighted) if weighted else base
            # 70/30 smoothing is the default prescribed in the specification.
            learned.append(round(max(0.55, min(1.55, base * 0.7 + observed * 0.3)), 4))
        return learned, evidence

    async def calculate(self, current_user: User, *, month: Optional[str], seller_external_id: Optional[str], seller_name: Optional[str], store_name: Optional[str]) -> dict:
        month_date, _, _ = self.kpi.month_range(month)
        today = date.today()
        if month_date.year != today.year or month_date.month != today.month:
            today = month_date
        month_end = (month_date.replace(year=month_date.year + 1, month=1) if month_date.month == 12 else month_date.replace(month=month_date.month + 1)) - timedelta(days=1)
        overview = await self.kpi.kpi_overview(current_user=current_user, month=month, store_name=store_name)
        rows = overview.get("sellers") or []
        seller = next((row for row in rows if seller_external_id and row.get("seller_external_id") == seller_external_id), None)
        if not seller and seller_name:
            normalized = self.kpi._normalize_seller_identity(seller_name)
            seller = next((row for row in rows if self.kpi._normalize_seller_identity(row.get("seller_name")) == normalized), None)
        if not seller:
            raise ValueError("Продавец не найден в доступных KPI-данных")
        seller_id = str(seller.get("seller_external_id") or "")
        if not seller_id:
            raise ValueError("Для продавца отсутствует идентификатор 1С")

        base_plan = float(seller.get("revenue_plan") or 0)
        net_fact = float(seller.get("revenue") or 0)
        store_id = seller.get("store_id")
        history = await self._history_daily_sales(seller_id=seller_id, store_id=store_id, today=today)
        learned_weekdays, evidence = self._learn_weekday_coefficients(history)
        returns_amount = sum(max(-float(row.get("net_revenue") or 0), 0) for row in history if row.get("sale_date", today).year == month_date.year and row.get("sale_date", today).month == month_date.month)
        working_target = base_plan * 1.2 if base_plan else 0.0
        remaining = max(working_target - net_fact, 0.0)
        remaining_days = [today + timedelta(days=offset) for offset in range((month_end - today).days + 1)]
        weights = []
        for day in remaining_days:
            weekday = learned_weekdays[day.weekday()]
            calendar = self._calendar_coefficient(day)
            pacing = self._pacing_coefficient(day, today, month_end)
            weights.append({"date": day, "weekday": weekday, "calendar": calendar, "pacing": pacing, "store": 1.0, "season": 1.0, "weight": weekday * calendar * pacing})
        today_weight = weights[0]
        weights_sum = sum(item["weight"] for item in weights) or 1.0
        mathematical_plan = remaining * today_weight["weight"] / weights_sum if remaining else 0.0
        average_history = sum(float(row.get("net_revenue") or 0) for row in history[-28:]) / min(len(history), 28) if history else 0.0
        expected_remaining = sum(average_history * item["weekday"] * item["calendar"] * item["pacing"] for item in weights)
        forecast = net_fact + expected_remaining
        base_percent = net_fact / base_plan * 100 if base_plan else None
        target_percent = net_fact / working_target * 100 if working_target else None
        gap = forecast - working_target if working_target else None
        required_daily = remaining / len(remaining_days) if remaining_days else 0.0
        avg_check = net_fact / float(seller.get("checks") or 1) if seller.get("checks") else 0.0
        items_per_check = float(seller.get("items_sold") or 0) / float(seller.get("checks") or 1) if seller.get("checks") else 0.0
        if seller.get("checks_plan") and float(seller.get("checks") or 0) < float(seller["checks_plan"]) * (today.day / month_end.day) * 0.9:
            focus = {"key": "checks", "title": "Количество чеков", "action": "Усильте вовлечение, примерку и персональные приглашения."}
        elif avg_check and base_plan and avg_check < (base_plan / max(float(seller.get("checks_plan") or 1), 1)) * 0.9:
            focus = {"key": "avg_check", "title": "Средний чек", "action": "Предлагайте второй акцент и готовые комплекты."}
        elif items_per_check < 1.5:
            focus = {"key": "items_per_check", "title": "Комплектность", "action": "Собирайте готовое решение из двух и более изделий."}
        else:
            focus = {"key": "quality", "title": "Качество продаж", "action": "Поддерживайте средний чек и персональную работу с каждым гостем."}
        warnings = []
        if not base_plan:
            warnings.append("Нет утверждённого личного месячного плана: расчёт цели и выполнения неполный.")
        if not history:
            warnings.append("Недостаточно истории для адаптации коэффициентов: применены стартовые коэффициенты GLAME.")
        if returns_amount == 0:
            warnings.append("Возвраты в доступных строках не обнаружены; убедитесь, что данные 1С синхронизированы.")
        return {
            "calculation_date": today.isoformat(), "seller_name": seller.get("seller_name"), "store_name": seller.get("store_name"),
            "monthly_plan": round(base_plan, 2), "working_monthly_target": round(working_target, 2), "net_sales_fact": round(net_fact, 2), "returns_amount": round(returns_amount, 2),
            "remaining_to_target": round(remaining, 2), "daily_plan_math": self._round_money(mathematical_plan), "daily_plan_managerial": self._round_money(mathematical_plan),
            "required_daily_average": self._round_money(required_daily), "forecast_month_total": round(forecast, 2), "base_plan_completion_percent": round(base_percent, 1) if base_percent is not None else None,
            "working_target_completion_percent": round(target_percent, 1) if target_percent is not None else None, "target_gap_amount": round(gap, 2) if gap is not None else None,
            "target_gap_percent": round(forecast / working_target * 100 - 100, 1) if working_target else None,
            "coefficients": {"weekday": today_weight["weekday"], "calendar": today_weight["calendar"], "pacing": today_weight["pacing"], "season": 1.0, "store": 1.0, "remaining_weights_sum": round(weights_sum, 4), "learned_weekdays": learned_weekdays, "evidence": evidence},
            "kpi_focus": focus, "warnings": warnings,
            "explanation": "План дня — доля остатка до рабочей цели (+20% к месячному плану), распределённая по весам оставшихся дней: день недели × календарь × front-loaded pacing.",
        }
