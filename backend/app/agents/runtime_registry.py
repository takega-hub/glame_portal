"""Runtime metadata for GLAME AI agents.

This module bridges business-facing canonical agent IDs with the current
technical execution handlers. It intentionally has no database, FastAPI or
service imports so tests and future workers can import it safely.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.agents.contracts import (
    CANONICAL_AGENT_IDS,
    MARKETING_AGENT_REGISTRY,
    board_aliases,
    canonical_agent_id,
    execution_agent_id,
    prompt_agent_id,
)


@dataclass(frozen=True)
class RuntimeAgentSpec:
    """Executable/runtime metadata for one canonical GLAME agent."""

    canonical_agent_id: str
    name: str
    board_id: str
    prompt_agent_id: str
    execution_agent_id: str
    process_handler: str
    supports_task_process: bool
    aliases: List[str]


BOARD_ID_BY_CANONICAL_AGENT_ID: Dict[str, str] = {
    "director-agent": "command",
    "personal-media-agent": "personal-media",
    "brand-media-agent": "content",
    "crm-agent": "crm",
    "pr-partnerships-agent": "partnership",
    "traffic-growth-agent": "traffic",
    "analytics-agent": "analytics",
    "assortment-agent": "product",
}


PROCESS_HANDLER_BY_EXECUTION_AGENT_ID: Dict[str, str] = {
    "director-agent": "director",
    "content-agent": "content",
    "communication-agent": "communication",
    "analytics-agent": "analytics",
    "marketing-inventory-agent": "assortment_matrix",
}


EXTRA_SUPPORTED_PROCESS_AGENT_IDS: List[str] = [
    "inventory-procurement-agent",
    "inventory-control-agent",
    "clearance-agent",
    "assortment-matrix-agent",
    "merchandising-agent",
    "pricing-agent",
]


CHAT_ONLY_HANDLER = "task_chat_only"


def _build_runtime_agent_registry() -> Dict[str, RuntimeAgentSpec]:
    registry: Dict[str, RuntimeAgentSpec] = {}
    for agent in MARKETING_AGENT_REGISTRY:
        canonical_id = agent["id"]
        board_id = BOARD_ID_BY_CANONICAL_AGENT_ID[canonical_id]
        execution_id = execution_agent_id(canonical_id)
        handler = PROCESS_HANDLER_BY_EXECUTION_AGENT_ID.get(execution_id, CHAT_ONLY_HANDLER)
        registry[canonical_id] = RuntimeAgentSpec(
            canonical_agent_id=canonical_id,
            name=agent["name"],
            board_id=board_id,
            prompt_agent_id=prompt_agent_id(canonical_id),
            execution_agent_id=execution_id,
            process_handler=handler,
            supports_task_process=handler != CHAT_ONLY_HANDLER,
            aliases=list(agent.get("aliases", [])) + board_aliases(board_id),
        )
    return registry


_RUNTIME_AGENT_REGISTRY: Dict[str, RuntimeAgentSpec] = _build_runtime_agent_registry()


def get_runtime_agent_registry() -> Dict[str, RuntimeAgentSpec]:
    """Return runtime metadata for all canonical marketing agents."""

    return dict(_RUNTIME_AGENT_REGISTRY)


def get_runtime_agent_spec(agent_id: str) -> RuntimeAgentSpec:
    """Resolve a canonical, legacy or board alias to a runtime spec."""

    canonical_id = canonical_agent_id(agent_id)
    spec = _RUNTIME_AGENT_REGISTRY.get(canonical_id)
    if spec:
        return spec

    for candidate in _RUNTIME_AGENT_REGISTRY.values():
        if agent_id == candidate.execution_agent_id or agent_id in candidate.aliases:
            return candidate

    raise KeyError(f"Unknown GLAME AI agent: {agent_id}")


def runtime_execution_agent_id(agent_id: str) -> str:
    """Resolve the current technical execution ID for an agent or alias."""

    return get_runtime_agent_spec(agent_id).execution_agent_id


def runtime_prompt_agent_id(agent_id: str) -> str:
    """Resolve the prompt storage ID for an agent or alias."""

    return get_runtime_agent_spec(agent_id).prompt_agent_id


def supported_process_agent_ids() -> List[str]:
    """Return technical agent IDs that currently have /process handlers."""

    ids = {
        spec.execution_agent_id
        for spec in _RUNTIME_AGENT_REGISTRY.values()
        if spec.supports_task_process
    }
    ids.update(EXTRA_SUPPORTED_PROCESS_AGENT_IDS)
    return sorted(ids)


def canonical_process_agent_ids() -> List[str]:
    """Return canonical agents with implemented task processing."""

    return sorted(
        canonical_id
        for canonical_id, spec in _RUNTIME_AGENT_REGISTRY.items()
        if spec.supports_task_process
    )


# Import-light sanity guard: registry must stay aligned with contracts.
if set(_RUNTIME_AGENT_REGISTRY.keys()) != set(CANONICAL_AGENT_IDS):  # pragma: no cover
    raise RuntimeError("Runtime registry is out of sync with canonical GLAME agent IDs")
