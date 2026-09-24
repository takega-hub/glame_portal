"""Read-only daily monitoring for the Traffic & Growth board.

The service may read Yandex Direct and GLAME analytics, but it never creates,
edits, pauses, moderates or starts advertising campaigns.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advertising_connection import AdvertisingConnection
from app.models.advertising_daily_metric import AdvertisingDailyMetric
from app.models.agent_interaction import AgentInteractionLog, AgentInteractionTask, InteractionStatus


async def run_traffic_daily_reporting(db: AsyncSession, task: AgentInteractionTask) -> Dict[str, Any]:
    """Synchronize eligible Direct connections and persist a factual daily report."""
    # Import lazily: marketing imports models used by the web API, while the cron
    # registry imports this service at run time.
    from app.api.marketing import _decrypt_yandex_secret, _get_app_setting, _sync_yandex_direct_campaigns, _sync_yandex_direct_daily_metrics

    now = datetime.now(timezone.utc)
    connections = (
        await db.execute(
            select(AdvertisingConnection).where(
                AdvertisingConnection.platform == "yandex_direct",
                AdvertisingConnection.is_active.is_(True),
                AdvertisingConnection.status == "connected",
            )
        )
    ).scalars().all()
    sync_results: List[Dict[str, Any]] = []
    for connection in connections:
        encrypted = await _get_app_setting(db, f"yandex_oauth_token_{connection.id}")
        token = _decrypt_yandex_secret(encrypted or "")
        if not token:
            sync_results.append({"connection": connection.name, "status": "skipped", "reason": "authorization_required"})
            continue
        try:
            campaigns = await _sync_yandex_direct_campaigns(db, connection, token, None)
            metrics = await _sync_yandex_direct_daily_metrics(db, connection, token)
            connection.last_sync_at = now
            connection.last_sync_status = "scheduled_read_only_success"
            connection.last_sync_summary = {"campaigns_imported": campaigns["received"], "created": campaigns["created"], "updated": campaigns["updated"], "metric_rows": metrics["upserted"], "mode": "scheduled_read_only"}
            sync_results.append({"connection": connection.name, "status": "success", "campaigns": campaigns, "metrics": metrics})
        except Exception as exc:  # Keep the other connections and report the failure.
            connection.last_sync_at = now
            connection.last_sync_status = "scheduled_read_only_error"
            connection.last_sync_summary = {"message": str(exc)[:500], "mode": "scheduled_read_only"}
            sync_results.append({"connection": connection.name, "status": "error", "reason": str(exc)[:500]})

    period_start = now.date() - timedelta(days=13)
    totals_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(AdvertisingDailyMetric.impressions), 0),
                func.coalesce(func.sum(AdvertisingDailyMetric.clicks), 0),
                func.coalesce(func.sum(AdvertisingDailyMetric.cost), 0.0),
                func.coalesce(func.sum(AdvertisingDailyMetric.conversions), 0.0),
                func.max(AdvertisingDailyMetric.metric_date),
            ).where(AdvertisingDailyMetric.metric_date >= period_start)
        )
    ).one()
    impressions, clicks, cost, conversions, latest_metric_date = totals_row
    ctr = round((float(clicks or 0) / float(impressions) * 100), 2) if impressions else 0.0
    cpc = round(float(cost or 0) / float(clicks), 2) if clicks else 0.0
    failures = [item for item in sync_results if item["status"] != "success"]
    freshness = "fresh" if latest_metric_date and latest_metric_date >= now.date() - timedelta(days=2) else "stale_or_empty"
    checkpoint_reviews: List[Dict[str, Any]] = []
    traffic_tasks = (
        await db.execute(select(AgentInteractionTask).where(AgentInteractionTask.target_agent == "traffic-growth-agent"))
    ).scalars().all()
    for traffic_task in traffic_tasks:
        release = (traffic_task.task_context or {}).get("direct_production_release")
        if not isinstance(release, dict) or not release.get("moderation_requested_at"):
            continue
        try:
            started = datetime.fromisoformat(str(release["moderation_requested_at"]).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_days = max(0, (now - started).days)
        except (TypeError, ValueError):
            continue
        checkpoint = "day_3_diagnostic" if 3 <= age_days < 10 else "day_10_14_decision" if 10 <= age_days <= 14 else None
        if checkpoint:
            checkpoint_reviews.append({"task_id": str(traffic_task.id), "campaign_id": release.get("direct_campaign_id"), "age_days": age_days, "checkpoint": checkpoint, "action": "Подготовить диагностику и решение только на согласование; ставки и бюджет не менять автоматически."})
    summary = (
        f"Ежедневный отчёт Traffic & Growth за {now.date().isoformat()}: "
        f"показы {int(impressions or 0)}, клики {int(clicks or 0)}, расход {float(cost or 0):.2f} ₽, "
        f"CTR {ctr:.2f}%, CPC {cpc:.2f} ₽, конверсии {float(conversions or 0):.0f}. "
        f"Свежесть данных: {freshness}. Контрольных точек пилота: {len(checkpoint_reviews)}."
    )
    report = {
        "report_type": "daily",
        "generated_at": now.isoformat(),
        "period": {"from": period_start.isoformat(), "to": now.date().isoformat()},
        "totals": {"impressions": int(impressions or 0), "clicks": int(clicks or 0), "cost": float(cost or 0), "conversions": float(conversions or 0), "ctr": ctr, "cpc": cpc},
        "latest_metric_date": latest_metric_date.isoformat() if latest_metric_date else None,
        "freshness": freshness,
        "sync_results": sync_results,
        "diagnostics": ["Нет свежих дневных метрик — проверьте OAuth/доступ кабинета и статус синхронизации."] if freshness != "fresh" else ([f"Не удалось синхронизировать кабинеты: {', '.join(item['connection'] for item in failures)}."] if failures else []),
        "checkpoint_reviews": checkpoint_reviews,
        "safety": "read_only_sync_no_ad_changes",
    }
    task.status = InteractionStatus.COMPLETED.value
    task.started_at = now
    task.completed_at = now
    task.output_data = {"summary": summary, "traffic_report": report}
    task.output_metadata = {**(task.output_metadata or {}), "processed_by": "traffic-reporting-scheduler", "processed_at": now.isoformat(), "execution_mode": "read_only"}
    context = dict(task.task_context or {})
    context.update({"board": "traffic", "traffic_project_hidden": True, "report_type": "daily", "last_report_at": now.isoformat()})
    task.task_context = context
    db.add(AgentInteractionLog(task_id=task.id, agent_name="traffic-reporting-scheduler", event_type="traffic_daily_report_completed", event_data=report, message=summary))
    return report
