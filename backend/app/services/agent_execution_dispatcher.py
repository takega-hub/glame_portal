"""Small dispatcher facade for GLAME agent task execution routing.

The heavy task execution logic still lives in API/service handlers during this
migration. This facade centralizes the first routing decision so endpoints do
not duplicate canonical/legacy alias handling.
"""
from __future__ import annotations

from app.agents.runtime_registry import (
    RuntimeAgentSpec,
    get_runtime_agent_spec,
    runtime_execution_agent_id,
    supported_process_agent_ids,
)

PROCESS_ALLOWED_STATUSES = frozenset({"approved", "queued", "processing", "completed"})


class AgentExecutionDispatcher:
    """Resolve canonical GLAME agent IDs to current process handlers."""

    def resolve(self, agent_id: str) -> RuntimeAgentSpec:
        return get_runtime_agent_spec(agent_id)

    def resolve_process_agent_id(self, agent_id: str) -> str:
        """Return the technical process agent ID or raise for chat-only agents."""

        try:
            spec = self.resolve(agent_id)
        except KeyError:
            if agent_id in supported_process_agent_ids():
                return agent_id
            raise

        if not spec.supports_task_process:
            raise ValueError(
                f"Agent '{spec.canonical_agent_id}' currently supports task chat/board work, "
                "but has no dedicated /process handler yet."
            )
        return spec.execution_agent_id

    def require_process_handler(self, agent_id: str) -> RuntimeAgentSpec:
        """Return the runtime spec only when process execution is implemented."""

        spec = self.resolve(agent_id)
        if not spec.supports_task_process:
            raise ValueError(
                f"Agent '{spec.canonical_agent_id}' currently supports task chat/board work, "
                "but has no dedicated /process handler yet."
            )
        return spec

    def is_process_supported(self, agent_id: str) -> bool:
        try:
            self.resolve_process_agent_id(agent_id)
        except (KeyError, ValueError):
            return False
        return True

    def require_process_status_allowed(self, status: str) -> None:
        """Reject unsafe direct processing before approval/queue lifecycle."""

        normalized = (status or "").strip().lower()
        if normalized not in PROCESS_ALLOWED_STATUSES:
            raise ValueError(
                "Task must be approved or queued before processing. "
                f"Current status: {status or 'unknown'}."
            )


agent_execution_dispatcher = AgentExecutionDispatcher()


def resolve_execution_agent_id(agent_id: str) -> str:
    """Compatibility helper for endpoints during dispatcher migration."""

    try:
        return agent_execution_dispatcher.resolve_process_agent_id(agent_id)
    except ValueError:
        # Keep existing endpoint behavior for chat-only agents: route falls
        # through to the endpoint's explicit "not implemented" error.
        return runtime_execution_agent_id(agent_id)
