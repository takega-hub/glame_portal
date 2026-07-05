from __future__ import annotations

import subprocess
import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import require_admin
from app.models.user import User


router = APIRouter()
logger = logging.getLogger(__name__)


class PlatformRestartResponse(BaseModel):
    status: str
    service: str
    message: str
    restart_unit: Optional[str] = None


def _schedule_glame_stack_restart() -> str:
    """Schedule restart in a separate transient systemd unit.

    Running `systemctl restart glame-stack` directly from inside the same
    service is fragile: the caller is killed while the HTTP response is still
    being finalized and failures can be hidden. A transient unit survives the
    current backend process and makes the restart visible in journalctl.
    """

    unit_name = f"glame-stack-restart-{int(time.time())}"
    command = [
        "systemd-run",
        f"--unit={unit_name}",
        "--description=Restart GLAME stack requested from admin UI",
        "--collect",
        "--on-active=2",
        "/bin/systemctl",
        "restart",
        "glame-stack.service",
    ]
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        logger.error(
            "Failed to schedule glame-stack restart: rc=%s stdout=%s stderr=%s",
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "systemd-run failed")
    logger.warning("Scheduled glame-stack restart via transient unit %s", unit_name)
    return f"{unit_name}.service"


@router.post("/restart", response_model=PlatformRestartResponse)
async def restart_platform(
    _current_user: User = Depends(require_admin()),
) -> PlatformRestartResponse:
    try:
        restart_unit = _schedule_glame_stack_restart()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось запланировать перезапуск: {exc}")
    return PlatformRestartResponse(
        status="scheduled",
        service="glame-stack",
        restart_unit=restart_unit,
        message="Перезагрузка платформы запланирована через systemd. Интерфейс может быть недоступен 20–120 секунд.",
    )
