"""Canonical GLAME AI marketing agent registries.

The business-facing agent map is defined by
`docs/admin/GLAME_AI_Agent_System_Prompts_v1_2.md` and centralized in
`app.agents.contracts`. Runtime execution metadata is centralized in
`app.agents.runtime_registry` so API endpoints, workers and frontend schema
exporters can use one source of truth while legacy technical ids are migrated.
"""
from typing import Any, Dict, List

from app.agents.contracts import MARKETING_AGENT_REGISTRY
from app.agents.runtime_registry import get_runtime_agent_registry
from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env


def get_marketing_agent_registry() -> List[Dict[str, Any]]:
    return MARKETING_AGENT_REGISTRY


def get_marketing_agent_runtime_registry() -> List[Dict[str, Any]]:
    """Return canonical agent registry enriched with execution metadata."""

    runtime_by_id = get_runtime_agent_registry()
    hermes_runtime = HermesAgentRuntime(hermes_runtime_config_from_env())
    enriched: List[Dict[str, Any]] = []
    for agent in MARKETING_AGENT_REGISTRY:
        spec = runtime_by_id[agent["id"]]
        enriched.append(
            {
                **agent,
                "board_id": spec.board_id,
                "prompt_agent_id": spec.prompt_agent_id,
                "execution_agent_id": spec.execution_agent_id,
                "process_handler": spec.process_handler,
                "supports_task_process": spec.supports_task_process,
                "hermes_profile": hermes_runtime.profile_for_agent(agent["id"]),
            }
        )
    return enriched
