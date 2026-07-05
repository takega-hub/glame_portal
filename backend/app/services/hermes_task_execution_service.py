"""Feature-flagged task execution through Hermes Agent runtime.

Default mode is legacy so existing OpenRouter/direct handlers keep working until
GLAME explicitly enables Hermes with GLAME_AGENT_RUNTIME=hermes.
"""
from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from app.agents.runtime_registry import get_runtime_agent_spec, runtime_prompt_agent_id
from app.services.agent_execution_dispatcher import agent_execution_dispatcher
from app.services.hermes_agent_runtime import HermesAgentRuntime, HermesRunResult, hermes_runtime_config_from_env


class RuntimeMode(str, Enum):
    LEGACY = "legacy"
    HERMES = "hermes"


def agent_runtime_mode_from_env(env: Optional[Mapping[str, str]] = None) -> RuntimeMode:
    """Read the safe runtime feature flag. Unknown values fall back to legacy."""

    source = env or os.environ
    value = str(source.get("GLAME_AGENT_RUNTIME", RuntimeMode.LEGACY.value)).strip().lower()
    if value == RuntimeMode.HERMES.value:
        return RuntimeMode.HERMES
    return RuntimeMode.LEGACY


def agent_runtime_status_from_env(env: Optional[Mapping[str, str]] = None) -> dict:
    """Return a redacted, API-safe view of the effective agent runtime mode."""

    source = env or os.environ
    raw_value = str(source.get("GLAME_AGENT_RUNTIME", "")).strip()
    mode = agent_runtime_mode_from_env(source)
    return {
        "runtime_mode": mode.value,
        "hermes_enabled": mode == RuntimeMode.HERMES,
        "raw_env_present": bool(raw_value),
        "raw_env_supported": raw_value.lower() in {RuntimeMode.LEGACY.value, RuntimeMode.HERMES.value} if raw_value else True,
    }


def _json_safe_datetime(value: Any) -> Optional[str]:
    return value.isoformat() if value else None


class HermesTaskExecutionService:
    """Execute approved GLAME agent tasks through Hermes when feature-flagged."""

    def __init__(
        self,
        runtime_mode: Optional[RuntimeMode] = None,
        runtime: Optional[HermesAgentRuntime] = None,
    ) -> None:
        self.runtime_mode = runtime_mode or agent_runtime_mode_from_env()
        self.runtime = runtime or HermesAgentRuntime(hermes_runtime_config_from_env())

    def should_handle(self, task: Any) -> bool:
        """Return True when Hermes mode is enabled for a known GLAME agent."""

        if self.runtime_mode != RuntimeMode.HERMES:
            return False
        try:
            get_runtime_agent_spec(task.target_agent)
        except KeyError:
            return agent_execution_dispatcher.is_process_supported(task.target_agent)
        return True

    def build_task_payload(self, task: Any) -> dict:
        """Preserve the GLAME task passport for the Hermes agent."""

        return {
            "id": str(task.id),
            "source_agent": task.source_agent,
            "target_agent": task.target_agent,
            "task_type": task.task_type,
            "task_context": task.task_context or {},
            "input_data": task.input_data or {},
            "target_metrics": task.target_metrics or {},
            "requirements": task.requirements or {},
            "constraints": task.constraints or {},
            "priority": task.priority,
            "status": task.status,
            "deadline_at": _json_safe_datetime(getattr(task, "deadline_at", None)),
        }

    async def execute(self, task: Any, db: Any) -> bool:
        """Run the task via Hermes if enabled. Returns False for legacy fallback."""

        if not self.should_handle(task):
            return False

        system_prompt = await self._load_active_system_prompt(task, db)
        payload = self.build_task_payload(task)
        result = await self.runtime.run_task(task.target_agent, system_prompt, payload)
        await self._apply_result(task, db, result)
        return True

    async def _load_active_system_prompt(self, task: Any, db: Any) -> str:
        prompt_agent_id = runtime_prompt_agent_id(task.target_agent)
        try:
            from sqlalchemy import select  # type: ignore
            from app.models.agent_system_prompt import AgentSystemPrompt  # type: ignore

            query = select(AgentSystemPrompt).where(
                AgentSystemPrompt.agent_type == prompt_agent_id,
                AgentSystemPrompt.is_active == True,  # noqa: E712 - SQLAlchemy expression
            )
        except Exception:
            query = None

        result = await db.execute(query)
        prompt = result.scalars().first()
        if not prompt:
            raise ValueError(f"Active system prompt not found for agent '{prompt_agent_id}'")
        return prompt.system_prompt

    async def _apply_result(self, task: Any, db: Any, result: HermesRunResult) -> None:
        if result.success:
            task.status = "completed"
            task.output_data = {
                "runtime": "hermes",
                "result": result.output,
            }
            task.output_metadata = {
                **(task.output_metadata or {}),
                "hermes_profile": result.profile,
                "exit_code": result.exit_code,
                "completed_at": datetime.utcnow().isoformat(),
            }
            event_type = "hermes_task_completed"
            message = "Hermes agent completed task"
        else:
            task.status = "failed"
            task.error_message = result.error or result.output or "Hermes task execution failed"
            task.error_details = {
                "runtime": "hermes",
                "hermes_profile": result.profile,
                "exit_code": result.exit_code,
                "stderr": result.error,
            }
            event_type = "hermes_task_failed"
            message = task.error_message

        db.add(self._make_log(task, result, event_type, message))
        await db.commit()

    def _make_log(self, task: Any, result: HermesRunResult, event_type: str, message: str) -> Any:
        data = {
            "runtime": "hermes",
            "profile": result.profile,
            "exit_code": result.exit_code,
            "success": result.success,
        }
        context = {"command_preview": result.command[:4]}
        try:
            from app.models.agent_interaction import AgentInteractionLog  # type: ignore

            return AgentInteractionLog(
                task_id=task.id,
                agent_name=task.target_agent,
                event_type=event_type,
                event_data=data,
                message=message,
                execution_context=context,
            )
        except Exception:
            return SimpleNamespace(
                task_id=task.id,
                agent_name=task.target_agent,
                event_type=event_type,
                event_data=data,
                message=message,
                execution_context=context,
            )
