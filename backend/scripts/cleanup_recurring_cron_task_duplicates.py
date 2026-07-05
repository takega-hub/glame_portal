#!/usr/bin/env python3
"""Merge duplicate active tasks created by recurring admin CRON jobs.

Keeps the oldest active task per recurrence key as the single operational card,
marks newer active duplicates as cancelled, and writes audit logs to both the
kept task and each cancelled duplicate. Completed/failed/deleted historical
items are left untouched.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text

from app.database.connection import AsyncSessionLocal
from app.models.agent_interaction import AgentInteractionLog, InteractionStatus
from app.services.cron_registry import _json_dumps, _recurrence_key_for_job, get_cron_job, seed_default_jobs


TERMINAL_STATUSES = (
    InteractionStatus.COMPLETED.value,
    InteractionStatus.FAILED.value,
    InteractionStatus.CANCELLED.value,
    InteractionStatus.DELETED.value,
)


async def _fetch_active_tasks(db, recurrence_keys: list[str]) -> list[dict[str, Any]]:
    if not recurrence_keys:
        return []
    result = await db.execute(
        text(
            """
            SELECT id, task_type, target_agent, status, task_context, input_data, created_at
            FROM agent_interaction_tasks
            WHERE status NOT IN :terminal_statuses
              AND (
                    task_context ->> 'recurrence_key' IN :recurrence_keys
                    OR task_context ->> 'cron_job_id' IN :cron_job_ids
                    OR (source_agent = 'cron-scheduler' AND task_type IN :task_types)
                  )
            ORDER BY task_type ASC, created_at ASC
            """
        ).bindparams(
            bindparam("terminal_statuses", expanding=True),
            bindparam("recurrence_keys", expanding=True),
            bindparam("cron_job_ids", expanding=True),
            bindparam("task_types", expanding=True),
        ),
        {
            "terminal_statuses": TERMINAL_STATUSES,
            "recurrence_keys": recurrence_keys,
            "cron_job_ids": [key.split(":", 1)[1] if ":" in key else key for key in recurrence_keys],
            "task_types": [key.split(":", 1)[0] for key in recurrence_keys],
        },
    )
    return [dict(row) for row in result.mappings().all()]


def _key_for_row(row: dict[str, Any], known_task_type_to_key: dict[str, str]) -> str | None:
    ctx = row.get("task_context") or {}
    if ctx.get("recurrence_key"):
        return str(ctx["recurrence_key"])
    if ctx.get("cron_job_id"):
        return f"{row.get('task_type')}:{ctx['cron_job_id']}"
    return known_task_type_to_key.get(str(row.get("task_type") or ""))


async def cleanup(job_id: str, apply: bool) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        await seed_default_jobs(db)
        job = await get_cron_job(db, job_id)
        if not job:
            raise SystemExit(f"CRON job not found: {job_id}")

        recurrence_key = _recurrence_key_for_job(job)
        rows = await _fetch_active_tasks(db, [recurrence_key])
        known_task_type_to_key = {str(job["task_type"]): recurrence_key}
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = _key_for_row(row, known_task_type_to_key)
            if key == recurrence_key:
                grouped[key].append(row)

        now = datetime.now(timezone.utc)
        report: dict[str, Any] = {
            "job_id": job_id,
            "recurrence_key": recurrence_key,
            "apply": apply,
            "active_found": len(grouped.get(recurrence_key, [])),
            "kept_task_id": None,
            "cancelled_duplicates": [],
        }
        tasks = grouped.get(recurrence_key, [])
        if not tasks:
            return report

        keep = tasks[0]
        duplicates = tasks[1:]
        report["kept_task_id"] = str(keep["id"])
        report["cancelled_duplicates"] = [str(row["id"]) for row in duplicates]

        if not apply:
            return report

        keep_ctx = dict(keep.get("task_context") or {})
        history = list(keep_ctx.get("run_history") or [])
        for row in duplicates:
            history.append(
                {
                    "run_at": row["created_at"].isoformat() if row.get("created_at") else now.isoformat(),
                    "cron_job_id": job_id,
                    "manual": False,
                    "event": "merged_duplicate_recurring_task",
                    "duplicate_task_id": str(row["id"]),
                    "duplicate_status": row.get("status"),
                }
            )
        keep_ctx.update(
            {
                "cron_job_id": job_id,
                "cron_title": job["title"],
                "cron_category": job["category"],
                "schedule_type": job["schedule_type"],
                "created_from": "admin_cron",
                "is_recurring": True,
                "recurrence_key": recurrence_key,
                "last_deduped_at": now.isoformat(),
                "run_count": max(int(keep_ctx.get("run_count") or 1), len(tasks)),
                "run_history": history[-50:],
            }
        )
        await db.execute(
            text(
                """
                UPDATE agent_interaction_tasks
                SET task_context = CAST(:task_context AS json),
                    updated_at = now()
                WHERE id = :task_id
                """
            ),
            {"task_id": str(keep["id"]), "task_context": _json_dumps(keep_ctx)},
        )
        db.add(
            AgentInteractionLog(
                task_id=keep["id"],
                agent_name="cron-scheduler",
                event_type="recurring_task_duplicates_merged",
                event_data={
                    "job_id": job_id,
                    "recurrence_key": recurrence_key,
                    "duplicate_task_ids": [str(row["id"]) for row in duplicates],
                },
                message=f"Объединены дубли регулярной задачи: {job['title']}",
            )
        )

        for row in duplicates:
            dup_ctx = dict(row.get("task_context") or {})
            dup_ctx.update(
                {
                    "recurrence_key": recurrence_key,
                    "merged_into_task_id": str(keep["id"]),
                    "merged_at": now.isoformat(),
                }
            )
            await db.execute(
                text(
                    """
                    UPDATE agent_interaction_tasks
                    SET status = :status,
                        task_context = CAST(:task_context AS json),
                        error_message = :reason,
                        completed_at = :completed_at,
                        updated_at = now()
                    WHERE id = :task_id
                    """
                ),
                {
                    "task_id": str(row["id"]),
                    "status": InteractionStatus.CANCELLED.value,
                    "task_context": _json_dumps(dup_ctx),
                    "reason": "Дубль регулярной CRON-задачи; объединено в одну карточку.",
                    "completed_at": now,
                },
            )
            db.add(
                AgentInteractionLog(
                    task_id=row["id"],
                    agent_name="cron-scheduler",
                    event_type="recurring_task_duplicate_cancelled",
                    event_data={
                        "job_id": job_id,
                        "recurrence_key": recurrence_key,
                        "merged_into_task_id": str(keep["id"]),
                    },
                    message=f"Дубль регулярной задачи объединен с основной карточкой: {job['title']}",
                )
            )

        await db.commit()
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", default="onec_data_sync_monitor")
    parser.add_argument("--apply", action="store_true", help="Actually update DB; without it only prints a plan")
    args = parser.parse_args()
    report = asyncio.run(cleanup(args.job_id, args.apply))
    import json

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
