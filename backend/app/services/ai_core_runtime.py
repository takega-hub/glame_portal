"""AI core runtime selection for GLAME agents.

The task runtime flag (`GLAME_AGENT_RUNTIME`) controls how task cards are
processed. This module controls the conversational/generation core used by
BaseAgent: OpenRouter directly, Hermes profiles, or a local OpenAI-compatible
LLM endpoint.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any, Mapping, Optional

import httpx

from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env


class AiCoreRuntime(str, Enum):
    OPENROUTER = "openrouter"
    HERMES = "hermes"
    LOCAL = "local"


SUPPORTED_AI_CORE_RUNTIMES = {runtime.value for runtime in AiCoreRuntime}


def _normalize_ai_core_runtime(value: Optional[str]) -> Optional[AiCoreRuntime]:
    normalized = str(value or "").strip().lower()
    if normalized == AiCoreRuntime.HERMES.value:
        return AiCoreRuntime.HERMES
    if normalized == AiCoreRuntime.LOCAL.value:
        return AiCoreRuntime.LOCAL
    if normalized == AiCoreRuntime.OPENROUTER.value:
        return AiCoreRuntime.OPENROUTER
    return None


def ai_core_runtime_from_env(env: Optional[Mapping[str, str]] = None) -> AiCoreRuntime:
    """Read AI core from env, falling back to Hermes when task runtime is Hermes."""

    source = env or os.environ
    explicit = _normalize_ai_core_runtime(source.get("GLAME_AI_CORE"))
    if explicit:
        return explicit
    if str(source.get("GLAME_AGENT_RUNTIME", "")).strip().lower() == AiCoreRuntime.HERMES.value:
        return AiCoreRuntime.HERMES
    return AiCoreRuntime.OPENROUTER


async def get_ai_core_runtime() -> tuple[AiCoreRuntime, str]:
    """Return effective AI core runtime and source (`db`, `env`, or `default`)."""

    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.models.app_setting import AppSetting

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(AppSetting).where(AppSetting.key == "ai_core_runtime"))
            setting = result.scalar_one_or_none()
            runtime = _normalize_ai_core_runtime(getattr(setting, "value", None))
            if runtime:
                return runtime, "db"
    except Exception:
        pass

    runtime = ai_core_runtime_from_env()
    if os.getenv("GLAME_AI_CORE") or os.getenv("GLAME_AGENT_RUNTIME"):
        return runtime, "env"
    return runtime, "default"


async def generate_agent_text(
    *,
    agent_id: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 3000,
    **kwargs: Any,
) -> str:
    """Generate text through the selected AI core for a concrete GLAME agent."""

    runtime, _source = await get_ai_core_runtime()
    if runtime == AiCoreRuntime.HERMES:
        result = await HermesAgentRuntime(hermes_runtime_config_from_env()).run_task(
            agent_id=agent_id,
            system_prompt=system_prompt or "",
            task_payload={
                "task_type": "agent_generation",
                "prompt": prompt,
                "max_tokens": max_tokens,
                "generation_options": kwargs,
            },
        )
        if result.success:
            return result.output
        raise ValueError(
            f"Hermes generation failed for {agent_id} "
            f"(profile={result.profile}, exit_code={result.exit_code}): "
            f"{result.error or result.output}"
        )

    if runtime == AiCoreRuntime.LOCAL:
        base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        local_model = str(model or os.getenv("LOCAL_LLM_MODEL", "llama3.1")).strip()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": local_model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", 0.7),
            "max_tokens": max_tokens,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('LOCAL_LLM_API_KEY', 'local')}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
        return content if isinstance(content, str) else ""

    from app.services.llm_service import llm_service

    return await llm_service.generate(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        **kwargs,
    )
