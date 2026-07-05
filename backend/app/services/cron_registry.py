import asyncio
import logging
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
from app.models.agent_interaction import AgentInteractionLog, AgentInteractionTask, InteractionStatus, TaskPriority

logger = logging.getLogger(__name__)


DEFAULT_CRON_JOBS: List[Dict[str, Any]] = [
    {
        "id": "daily_plan_approval",
        "title": "Ежедневный план на завтра",
        "description": "Директор собирает состояние задач, данные по агентам и готовит план на завтра на согласование.",
        "category": "director",
        "target_agent": "director-agent",
        "task_type": "tomorrow_plan_preparation",
        "schedule_type": "daily",
        "time_of_day": "19:00",
        "weekday": None,
        "day_of_month": None,
        "enabled": True,
        "parameters": {"approval_required": True, "report_scope": "tasks_and_next_day_plan"},
    },
    {
        "id": "birthday_customers_check",
        "title": "Проверка клиентов с ДР",
        "description": "AI CRM ищет клиентов с ближайшим днем рождения и готовит сегмент/сценарий на согласование.",
        "category": "crm",
        "target_agent": "crm-agent",
        "task_type": "crm_birthday_check",
        "schedule_type": "daily",
        "time_of_day": "09:00",
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"days_ahead": 7, "create_segment": True, "approval_required": True},
    },
    {
        "id": "loyalty_reactivation_check",
        "title": "Лояльность и возврат клиентов",
        "description": "AI CRM проверяет баллы, спящие сегменты и готовит предложения коммуникаций без автоматической отправки.",
        "category": "crm",
        "target_agent": "crm-agent",
        "task_type": "crm_loyalty_reactivation_check",
        "schedule_type": "daily",
        "time_of_day": "10:00",
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"approval_required": True, "no_mass_send_without_admin_approval": True},
    },
    {
        "id": "new_arrivals_campaign_check",
        "title": "Поступления для CRM/контента",
        "description": "AI Assortment проверяет новые поступления, а директор решает, нужны ли CRM, контент или витринные задачи.",
        "category": "assortment",
        "target_agent": "assortment-agent",
        "task_type": "new_arrivals_marketing_check",
        "schedule_type": "daily",
        "time_of_day": "11:00",
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"approval_required": True, "handoff_to_director": True},
    },
    {
        "id": "inventory_control",
        "title": "Контроль запасов",
        "description": "AI Assortment проверяет критические остатки, slow moving и товары для продвижения.",
        "category": "inventory",
        "target_agent": "assortment-agent",
        "task_type": "inventory_control_review",
        "schedule_type": "daily",
        "time_of_day": "08:30",
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"period": "month", "include_stock_risks": True},
    },
    {
        "id": "onec_data_sync_monitor",
        "title": "Контроль синхронизации 1С",
        "description": "Проверяет свежесть данных 1С: продажи, чеки, остатки, покупатели. При проблемах обновляет регулярную карточку и создает отдельный инцидент только для конкретной проблемы.",
        "category": "data",
        "target_agent": "analytics-agent",
        "task_type": "data_freshness_review",
        "schedule_type": "hourly",
        "time_of_day": None,
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {
            "sources": ["1c_sales", "1c_stock", "1c_customers"],
            "interval_minutes": 60,
            "recurrence_key": "data_freshness_review:onec_data_sync_monitor",
        },
    },
    {
        "id": "marketing_daily_analysis",
        "title": "Ежедневный маркетинговый анализ",
        "description": "AI Analytics собирает продажи, чеки, посещения магазинов, сайт/приложение/Instagram при наличии источников.",
        "category": "analytics",
        "target_agent": "analytics-agent",
        "task_type": "daily_marketing_analysis",
        "schedule_type": "daily",
        "time_of_day": "18:00",
        "weekday": None,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"period": "today", "approval_required": False},
    },
    {
        "id": "weekly_operational_review",
        "title": "Недельный operational review",
        "description": "Директор проводит недельный разбор задач, агентских результатов, блокеров и плана следующей недели.",
        "category": "director",
        "target_agent": "director-agent",
        "task_type": "weekly_operational_review",
        "schedule_type": "weekly",
        "time_of_day": "18:00",
        "weekday": 0,
        "day_of_month": None,
        "enabled": False,
        "parameters": {"approval_required": True, "include_agent_board_statuses": True},
    },
    {
        "id": "monthly_strategic_review",
        "title": "Месячный strategic review",
        "description": "Директор готовит стратегический обзор месяца: продажи, трафик, CRM, контент, ассортимент, риски.",
        "category": "director",
        "target_agent": "director-agent",
        "task_type": "monthly_strategic_review",
        "schedule_type": "monthly",
        "time_of_day": "18:00",
        "weekday": None,
        "day_of_month": 1,
        "enabled": False,
        "parameters": {"approval_required": True, "period": "previous_month"},
    },
]


async def ensure_cron_tables(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS admin_cron_jobs (
                id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                category VARCHAR(50) NOT NULL DEFAULT 'system',
                target_agent VARCHAR(64) NOT NULL,
                task_type VARCHAR(100) NOT NULL,
                schedule_type VARCHAR(20) NOT NULL,
                time_of_day VARCHAR(5),
                weekday INTEGER,
                day_of_month INTEGER,
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                next_run_at TIMESTAMPTZ,
                last_run_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS admin_cron_runs (
                id UUID PRIMARY KEY,
                job_id VARCHAR(100) NOT NULL,
                status VARCHAR(30) NOT NULL,
                manual BOOLEAN NOT NULL DEFAULT FALSE,
                task_id UUID,
                message TEXT,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
    )


def _parse_time(value: Optional[str]) -> time:
    if not value:
        return time(9, 0)
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    except Exception:
        return time(9, 0)


def compute_next_run(job: Dict[str, Any], now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    schedule_type = job.get("schedule_type") or "daily"
    if schedule_type == "hourly":
        interval = int((job.get("parameters") or {}).get("interval_minutes") or 60)
        return now + timedelta(minutes=max(interval, 5))

    run_time = _parse_time(job.get("time_of_day"))
    candidate = datetime.combine(now.date(), run_time, tzinfo=timezone.utc)

    if schedule_type == "weekly":
        target_weekday = int(job.get("weekday") if job.get("weekday") is not None else 0)
        days_ahead = (target_weekday - now.weekday()) % 7
        candidate = candidate + timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    if schedule_type == "monthly":
        day = max(1, min(int(job.get("day_of_month") or 1), 28))
        candidate = candidate.replace(day=day)
        if candidate <= now:
            month = candidate.month + 1
            year = candidate.year
            if month > 12:
                month = 1
                year += 1
            candidate = candidate.replace(year=year, month=month, day=day)
        return candidate

    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def seed_default_jobs(db: AsyncSession) -> None:
    await ensure_cron_tables(db)
    for job in DEFAULT_CRON_JOBS:
        next_run_at = compute_next_run(job) if job.get("enabled") else None
        await db.execute(
            text(
                """
                INSERT INTO admin_cron_jobs (
                    id, title, description, category, target_agent, task_type,
                    schedule_type, time_of_day, weekday, day_of_month, enabled,
                    parameters, next_run_at, updated_at
                )
                VALUES (
                    :id, :title, :description, :category, :target_agent, :task_type,
                    :schedule_type, :time_of_day, :weekday, :day_of_month, :enabled,
                    CAST(:parameters AS jsonb), :next_run_at, now()
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {**job, "parameters": _json_dumps(job.get("parameters") or {}), "next_run_at": next_run_at},
        )


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)


def _row_to_job(row: Any) -> Dict[str, Any]:
    data = dict(row)
    data["parameters"] = data.get("parameters") or {}
    for field in ("next_run_at", "last_run_at", "updated_at"):
        value = data.get(field)
        if isinstance(value, datetime):
            data[field] = value.isoformat()
    return data


async def list_cron_jobs(db: AsyncSession) -> List[Dict[str, Any]]:
    await seed_default_jobs(db)
    result = await db.execute(text("SELECT * FROM admin_cron_jobs ORDER BY category, title"))
    return [_row_to_job(row) for row in result.mappings().all()]


async def get_cron_job(db: AsyncSession, job_id: str) -> Optional[Dict[str, Any]]:
    await seed_default_jobs(db)
    result = await db.execute(text("SELECT * FROM admin_cron_jobs WHERE id = :id"), {"id": job_id})
    row = result.mappings().first()
    return _row_to_job(row) if row else None


def _make_job_id(title: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "_", (title or "cron_job").strip().lower())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return (raw[:70] or "cron_job") + "_" + uuid.uuid4().hex[:8]


async def create_cron_job(db: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    await seed_default_jobs(db)
    job_id = str(payload.get("id") or "").strip() or _make_job_id(str(payload.get("title") or "cron_job"))
    existing = await get_cron_job(db, job_id)
    if existing:
        raise ValueError("cron_job_exists")

    job = {
        "id": job_id[:100],
        "title": str(payload.get("title") or "Новый регламент")[:200],
        "description": payload.get("description") or "",
        "category": payload.get("category") or "system",
        "target_agent": payload.get("target_agent") or "director-agent",
        "task_type": payload.get("task_type") or "scheduled_admin_task",
        "schedule_type": payload.get("schedule_type") or "daily",
        "time_of_day": payload.get("time_of_day") or "09:00",
        "weekday": payload.get("weekday"),
        "day_of_month": payload.get("day_of_month"),
        "enabled": bool(payload.get("enabled") or False),
        "parameters": payload.get("parameters") or {},
    }
    job["next_run_at"] = compute_next_run(job) if job.get("enabled") else None
    await db.execute(
        text(
            """
            INSERT INTO admin_cron_jobs (
                id, title, description, category, target_agent, task_type,
                schedule_type, time_of_day, weekday, day_of_month, enabled,
                parameters, next_run_at, updated_at
            )
            VALUES (
                :id, :title, :description, :category, :target_agent, :task_type,
                :schedule_type, :time_of_day, :weekday, :day_of_month, :enabled,
                CAST(:parameters AS jsonb), :next_run_at, now()
            )
            """
        ),
        {**job, "parameters": _json_dumps(job.get("parameters") or {})},
    )
    refreshed = await get_cron_job(db, job["id"])
    return refreshed or job


async def update_cron_job(db: AsyncSession, job_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    job = await get_cron_job(db, job_id)
    if not job:
        raise ValueError("cron_job_not_found")
    updated = {**job, **{k: v for k, v in patch.items() if v is not None}}
    updated["next_run_at"] = compute_next_run(updated) if updated.get("enabled") else None
    await db.execute(
        text(
            """
            UPDATE admin_cron_jobs
            SET title = :title,
                description = :description,
                category = :category,
                target_agent = :target_agent,
                task_type = :task_type,
                schedule_type = :schedule_type,
                time_of_day = :time_of_day,
                weekday = :weekday,
                day_of_month = :day_of_month,
                enabled = :enabled,
                parameters = CAST(:parameters AS jsonb),
                next_run_at = :next_run_at,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            **updated,
            "parameters": _json_dumps(updated.get("parameters") or {}),
            "next_run_at": updated.get("next_run_at"),
        },
    )
    refreshed = await get_cron_job(db, job_id)
    return refreshed or updated


def _recurrence_key_for_job(job: Dict[str, Any]) -> str:
    parameters = job.get("parameters") or {}
    explicit_key = str(parameters.get("recurrence_key") or "").strip()
    if explicit_key:
        return explicit_key[:200]
    return f"{job.get('task_type') or 'scheduled_admin_task'}:{job.get('id') or job.get('title') or 'cron_job'}"[:200]


async def _find_active_recurring_task(db: AsyncSession, recurrence_key: str) -> Optional[AgentInteractionTask]:
    if not recurrence_key:
        return None
    terminal_statuses = (
        InteractionStatus.COMPLETED.value,
        InteractionStatus.FAILED.value,
        InteractionStatus.CANCELLED.value,
        InteractionStatus.DELETED.value,
    )
    result = await db.execute(
        text(
            """
            SELECT id
            FROM agent_interaction_tasks
            WHERE task_context ->> 'recurrence_key' = :recurrence_key
              AND status NOT IN :terminal_statuses
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).bindparams(bindparam("terminal_statuses", expanding=True)),
        {"recurrence_key": recurrence_key, "terminal_statuses": terminal_statuses},
    )
    task_id = result.scalar_one_or_none()
    if task_id is None:
        return None
    return await db.get(AgentInteractionTask, task_id)


async def list_cron_runs(db: AsyncSession, limit: int = 50) -> List[Dict[str, Any]]:
    await ensure_cron_tables(db)
    result = await db.execute(
        text(
            """
            SELECT r.*, j.title AS job_title
            FROM admin_cron_runs r
            LEFT JOIN admin_cron_jobs j ON j.id = r.job_id
            ORDER BY r.started_at DESC
            LIMIT :limit
            """
        ),
        {"limit": max(1, min(limit, 200))},
    )
    rows = []
    for row in result.mappings().all():
        data = dict(row)
        for field in ("started_at", "completed_at"):
            if isinstance(data.get(field), datetime):
                data[field] = data[field].isoformat()
        if data.get("task_id") is not None:
            data["task_id"] = str(data["task_id"])
        if data.get("id") is not None:
            data["id"] = str(data["id"])
        rows.append(data)
    return rows


async def run_cron_job(db: AsyncSession, job_id: str, manual: bool = False) -> Dict[str, Any]:
    job = await get_cron_job(db, job_id)
    if not job:
        raise ValueError("cron_job_not_found")

    now = datetime.now(timezone.utc)
    recurrence_key = _recurrence_key_for_job(job)
    existing_task = await _find_active_recurring_task(db, recurrence_key)
    is_reused_task = existing_task is not None
    if existing_task is not None:
        task = existing_task
        task_context = dict(task.task_context or {})
        run_history = list(task_context.get("run_history") or [])
        run_history.append(
            {
                "run_at": now.isoformat(),
                "cron_job_id": job["id"],
                "manual": manual,
                "event": "cron_retriggered_existing_task",
            }
        )
        task_context.update(
            {
                "cron_job_id": job["id"],
                "cron_title": job["title"],
                "cron_category": job["category"],
                "schedule_type": job["schedule_type"],
                "manual_run": manual,
                "created_from": "admin_cron",
                "is_recurring": True,
                "recurrence_key": recurrence_key,
                "last_cron_run_at": now.isoformat(),
                "run_count": int(task_context.get("run_count") or 1) + 1,
                "run_history": run_history[-50:],
            }
        )
        input_data = dict(task.input_data or {})
        input_data.update(
            {
                "title": job["title"],
                "description": job["description"],
                "parameters": job.get("parameters") or {},
                "expected_result": "Поддерживать одну регулярную карточку: фиксировать результат запуска, не создавать дубли; отдельные задачи создавать только для конкретных найденных проблем.",
            }
        )
        task.task_context = task_context
        task.input_data = input_data
        task.scheduled_at = now
    else:
        task = AgentInteractionTask(
            source_agent="cron-scheduler",
            target_agent=job["target_agent"],
            task_type=job["task_type"],
            task_context={
                "cron_job_id": job["id"],
                "cron_title": job["title"],
                "cron_category": job["category"],
                "schedule_type": job["schedule_type"],
                "manual_run": manual,
                "created_from": "admin_cron",
                "is_recurring": True,
                "recurrence_key": recurrence_key,
                "last_cron_run_at": now.isoformat(),
                "run_count": 1,
                "run_history": [
                    {
                        "run_at": now.isoformat(),
                        "cron_job_id": job["id"],
                        "manual": manual,
                        "event": "cron_created_recurring_task",
                    }
                ],
            },
            input_data={
                "title": job["title"],
                "description": job["description"],
                "parameters": job.get("parameters") or {},
                "expected_result": "Поддерживать одну регулярную карточку: фиксировать результат запуска, не создавать дубли; отдельные задачи создавать только для конкретных найденных проблем.",
            },
            requirements={
                "use_real_data_only": True,
                "show_sources": True,
                "no_mass_send_without_admin_approval": True,
                "do_not_create_duplicate_recurring_tasks": True,
                "create_separate_incident_only_for_actionable_problem": True,
            },
            priority=TaskPriority.NORMAL.value,
            status=InteractionStatus.PENDING.value,
            scheduled_at=now,
        )
        db.add(task)
    await db.flush()

    db.add(
        AgentInteractionLog(
            task_id=task.id,
            agent_name="cron-scheduler",
            event_type="cron_job_reused" if is_reused_task else "cron_job_triggered",
            event_data={
                "job_id": job["id"],
                "manual": manual,
                "target_agent": job["target_agent"],
                "recurrence_key": recurrence_key,
                "reused_existing_task": is_reused_task,
            },
            message=(
                f"CRON обновил регулярную задачу: {job['title']}"
                if is_reused_task
                else f"CRON запустил регламент: {job['title']}"
            ),
        )
    )

    run_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO admin_cron_runs (
                id, job_id, status, manual, task_id, message, started_at, completed_at, metadata
            )
            VALUES (
                :id, :job_id, 'queued', :manual, :task_id, :message, :started_at, :completed_at,
                CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "id": run_id,
            "job_id": job["id"],
            "manual": manual,
            "task_id": str(task.id),
            "message": (
                f"Обновлена регулярная задача для {job['target_agent']}"
                if is_reused_task
                else f"Создана задача для {job['target_agent']}"
            ),
            "started_at": now,
            "completed_at": now,
            "metadata": _json_dumps(
                {
                    "task_type": job["task_type"],
                    "parameters": job.get("parameters") or {},
                    "recurrence_key": recurrence_key,
                    "reused_existing_task": is_reused_task,
                }
            ),
        },
    )
    await db.execute(
        text(
            """
            UPDATE admin_cron_jobs
            SET last_run_at = :last_run_at,
                next_run_at = :next_run_at,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            "id": job["id"],
            "last_run_at": now,
            "next_run_at": compute_next_run(job, now) if job.get("enabled") else None,
        },
    )
    return {"run_id": run_id, "task_id": str(task.id), "job": job}


async def cron_scheduler_loop(stop_event: asyncio.Event) -> None:
    await asyncio.sleep(5)
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as db:
                await seed_default_jobs(db)
                now = datetime.now(timezone.utc)
                result = await db.execute(
                    text(
                        """
                        SELECT id
                        FROM admin_cron_jobs
                        WHERE enabled = TRUE
                          AND next_run_at IS NOT NULL
                          AND next_run_at <= :now
                        ORDER BY next_run_at ASC
                        LIMIT 5
                        """
                    ),
                    {"now": now},
                )
                due_ids = [row[0] for row in result.all()]
                for job_id in due_ids:
                    try:
                        await run_cron_job(db, job_id, manual=False)
                    except Exception:
                        logger.error("Admin CRON job failed: %s", job_id, exc_info=True)
                await db.commit()
        except Exception:
            logger.error("Admin CRON scheduler loop failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


async def start_admin_cron_scheduler(app) -> None:
    stop_event = asyncio.Event()
    task = asyncio.create_task(cron_scheduler_loop(stop_event))
    app.state.admin_cron_stop_event = stop_event
    app.state.admin_cron_task = task
    logger.info("Admin CRON scheduler started.")


async def stop_admin_cron_scheduler(app) -> None:
    stop_event = getattr(app.state, "admin_cron_stop_event", None)
    task = getattr(app.state, "admin_cron_task", None)
    if stop_event:
        stop_event.set()
    if task:
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("Admin CRON scheduler stopped.")
