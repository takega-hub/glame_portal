from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.user import User
from app.services.cron_registry import create_cron_job, list_cron_jobs, list_cron_runs, run_cron_job, update_cron_job

router = APIRouter()


class CronJobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None
    schedule_type: Optional[str] = Field(default=None, pattern="^(hourly|daily|weekly|monthly)$")
    time_of_day: Optional[str] = None
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=28)
    target_agent: Optional[str] = None
    task_type: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class CronJobCreate(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    category: str = "system"
    target_agent: str = "director-agent"
    task_type: str = "scheduled_admin_task"
    schedule_type: str = Field(default="daily", pattern="^(hourly|daily|weekly|monthly)$")
    time_of_day: Optional[str] = "09:00"
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=28)
    enabled: bool = False
    parameters: Dict[str, Any] = Field(default_factory=dict)


@router.get("/jobs")
async def get_cron_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(["admin", "ai_marketer", "content_manager"])),
):
    jobs = await list_cron_jobs(db)
    await db.commit()
    return {"jobs": jobs, "timezone": "UTC"}


@router.post("/jobs")
async def create_job(
    payload: CronJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(["admin", "ai_marketer", "content_manager"])),
):
    try:
        job = await create_cron_job(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        if str(exc) == "cron_job_exists":
            raise HTTPException(status_code=409, detail="CRON job already exists")
        raise
    await db.commit()
    return {"job": job}


@router.put("/jobs/{job_id}")
async def save_cron_job(
    job_id: str,
    payload: CronJobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(["admin", "ai_marketer", "content_manager"])),
):
    try:
        job = await update_cron_job(db, job_id, payload.model_dump(exclude_unset=True))
    except ValueError:
        raise HTTPException(status_code=404, detail="CRON job not found")
    await db.commit()
    return {"job": job}


@router.post("/jobs/{job_id}/run")
async def run_cron_job_now(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(["admin", "ai_marketer", "content_manager"])),
):
    try:
        result = await run_cron_job(db, job_id, manual=True)
    except ValueError:
        raise HTTPException(status_code=404, detail="CRON job not found")
    await db.commit()
    return result


@router.get("/runs")
async def get_cron_runs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(["admin", "ai_marketer", "content_manager"])),
):
    runs = await list_cron_runs(db, limit=limit)
    return {"runs": runs}
