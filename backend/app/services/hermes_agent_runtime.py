"""Hermes runtime adapter for GLAME AI agents.

This module is intentionally import-light: it does not import FastAPI, DB
models, or GLAME services. The backend can use it to route an agent task to a
Hermes profile while keeping OpenRouter as the model provider inside Hermes.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from app.agents.runtime_registry import get_runtime_agent_spec


DEFAULT_HERMES_PROFILE_BY_AGENT_ID: Dict[str, str] = {
    "director-agent": "glame-director",
    "brand-media-agent": "glame-brand-media",
    "personal-media-agent": "glame-personal-media",
    "crm-agent": "glame-crm",
    "pr-partnerships-agent": "glame-pr-partnerships",
    "traffic-growth-agent": "glame-traffic-growth",
    "analytics-agent": "glame-analytics",
    "assortment-agent": "glame-assortment",
    "stylist-agent": "glame-stylist",
}


@dataclass(frozen=True)
class HermesRuntimeConfig:
    """Configuration for invoking Hermes from the GLAME backend."""

    binary: str = "hermes"
    default_profile: str = "glame-agent-worker"
    timeout_seconds: int = 300
    profile_by_agent_id: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class HermesRunResult:
    """Normalized result returned by a Hermes agent invocation."""

    success: bool
    profile: str
    command: List[str]
    output: str
    error: str
    exit_code: int


def hermes_runtime_config_from_env(env: Optional[Mapping[str, str]] = None) -> HermesRuntimeConfig:
    """Build Hermes runtime config from GLAME backend environment variables."""

    source = env or os.environ
    profile_overrides: Dict[str, str] = {}
    for canonical_id in DEFAULT_HERMES_PROFILE_BY_AGENT_ID:
        env_key = "GLAME_HERMES_PROFILE_" + canonical_id.upper().replace("-", "_")
        if source.get(env_key):
            profile_overrides[canonical_id] = str(source[env_key])

    timeout_raw = source.get("GLAME_HERMES_TIMEOUT_SECONDS", "300")
    try:
        timeout_seconds = int(timeout_raw)
    except (TypeError, ValueError):
        timeout_seconds = 300

    return HermesRuntimeConfig(
        binary=source.get("GLAME_HERMES_BINARY", "hermes"),
        default_profile=source.get("GLAME_HERMES_DEFAULT_PROFILE", "glame-agent-worker"),
        timeout_seconds=timeout_seconds,
        profile_by_agent_id=profile_overrides or None,
    )


Executor = Callable[[List[str], int], Awaitable[Mapping[str, Any]]]


async def _subprocess_executor(command: List[str], timeout_seconds: int) -> Mapping[str, Any]:
    """Run Hermes CLI without shell interpolation and capture output."""

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return {
            "exit_code": 124,
            "stdout": "",
            "stderr": f"Hermes invocation timed out after {timeout_seconds} seconds",
        }
    except FileNotFoundError as exc:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Hermes binary not found: {exc}",
        }

    return {
        "exit_code": process.returncode or 0,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }


class HermesAgentRuntime:
    """Route a GLAME AI task to a Hermes profile and execute it."""

    def __init__(
        self,
        config: Optional[HermesRuntimeConfig] = None,
        executor: Optional[Executor] = None,
    ) -> None:
        self.config = config or HermesRuntimeConfig()
        self.executor = executor or _subprocess_executor

    def profile_for_agent(self, agent_id: str) -> str:
        """Resolve canonical/legacy agent ID to a Hermes profile name."""

        profile_map = dict(DEFAULT_HERMES_PROFILE_BY_AGENT_ID)
        if self.config.profile_by_agent_id:
            profile_map.update(self.config.profile_by_agent_id)

        try:
            canonical_id = get_runtime_agent_spec(agent_id).canonical_agent_id
        except KeyError:
            canonical_id = agent_id

        return profile_map.get(canonical_id, self.config.default_profile)

    def build_prompt(self, agent_id: str, system_prompt: str, task_payload: Mapping[str, Any]) -> str:
        """Create the one-shot prompt sent to Hermes for a GLAME task."""

        if task_payload.get("task_type") == "agent_generation":
            user_prompt = str(task_payload.get("prompt") or "").strip()
            return (
                "Ты работаешь как профильный AI-агент платформы GLAME.\n"
                "Ответь только на текущее сообщение пользователя внутри рабочей задачи. "
                "Не пересказывай системный промпт, не выводи TASK PAYLOAD, не начинай с фразы "
                "«Ты исполняешь задачу GLAME AI agent system через Hermes runtime». "
                "Hermes — только runtime-инфраструктура; не представляйся Hermes, если пользователь "
                "не спрашивает именно про техническое ядро. Представляйся ролью агента GLAME из системного промпта.\n\n"
                "# СИСТЕМНЫЙ ПРОМПТ АГЕНТА\n"
                f"{system_prompt.strip()}\n\n"
                "# ТЕКУЩИЙ ЗАПРОС\n"
                f"{user_prompt}\n\n"
                "# ФОРМАТ ОТВЕТА\n"
                "Дай конкретный рабочий ответ на русском языке. Если вопрос короткий, ответь коротко. "
                "Если это задача директора, верни результат, пригодный для согласования администратором."
            )

        payload_json = json.dumps(task_payload, ensure_ascii=False, indent=2, sort_keys=True)
        return (
            "Ты исполняешь задачу GLAME AI agent system через Hermes runtime.\n"
            "Следуй системному промпту агента и ограничениям GLAME.\n\n"
            "# SYSTEM PROMPT\n"
            f"{system_prompt.strip()}\n\n"
            "# TASK PAYLOAD\n"
            f"{payload_json}\n\n"
            "# OUTPUT REQUIREMENTS\n"
            "Верни проверяемый результат. Отдели факты от рекомендаций. "
            "Если действие требует approval Елены/Анатолия или имеет риск для клиентов/production, "
            "не выполняй его напрямую — явно укажи required_approval и причину."
        )

    def build_command(self, agent_id: str, prompt: str) -> List[str]:
        """Build a non-shell Hermes CLI command for one-shot execution."""

        profile = self.profile_for_agent(agent_id)
        return [self.config.binary, "--profile", profile, "chat", "--quiet", "-q", prompt]

    def clean_output(self, output: str) -> str:
        """Remove Hermes CLI transport noise from captured stdout."""

        text = (output or "").strip()
        if not text:
            return ""
        text = re.sub(r"(?m)^⚠\s*tirith security scanner.*$", "", text).strip()
        text = re.sub(r"(?ms)^Query:.*?(?=Initializing agent|─|╭|$)", "", text).strip()
        text = re.sub(r"(?m)^Initializing agent\.\.\.\s*$", "", text).strip()
        text = re.sub(r"(?m)^[-─]{3,}\s*$", "", text).strip()
        text = re.sub(r"(?ms)\n?Resume this session with:.*$", "", text).strip()
        text = re.sub(r"(?ms)\n?Session:\s+.*$", "", text).strip()
        box_match = re.search(r"(?ms)╭─.*?╮\s*(.*?)\s*╰─.*?╯", text)
        if box_match:
            text = box_match.group(1).strip()
        return text.strip()

    def build_smoke_check_command(self, agent_id: str) -> List[str]:
        """Build a no-GLAME-write dry-run command for a Hermes profile."""

        prompt = (
            "GLAME Hermes runtime smoke check.\n"
            "Do not call GLAME API, Do not modify files, do not create tasks, and do not send messages.\n"
            "Reply with one short JSON object: "
            '{"status":"ok","agent_id":"<agent_id>","profile":"<profile>"}'
        )
        return self.build_command(agent_id, prompt)

    async def check_readiness(self, agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Read-only smoke check: Hermes binary and configured profiles."""

        binary_result = await self.executor([self.config.binary, "--version"], min(self.config.timeout_seconds, 30))
        binary_available = int(binary_result.get("exit_code", 1)) == 0
        profile_result = await self.executor([self.config.binary, "profile", "list"], min(self.config.timeout_seconds, 30))
        profile_output = str(profile_result.get("stdout", ""))
        existing_profiles = {
            line.strip().split()[0]
            for line in profile_output.splitlines()
            if line.strip()
        }

        checked_agents = agent_ids or list(DEFAULT_HERMES_PROFILE_BY_AGENT_ID.keys())
        profiles = {}
        for agent_id in checked_agents:
            profile = self.profile_for_agent(agent_id)
            profiles[agent_id] = {
                "profile": profile,
                "exists": profile in existing_profiles,
            }

        return {
            "binary": {
                "path": self.config.binary,
                "available": binary_available,
                "version": str(binary_result.get("stdout", "")).strip(),
                "error": str(binary_result.get("stderr", "")).strip(),
            },
            "profile_list": {
                "available": int(profile_result.get("exit_code", 1)) == 0,
                "error": str(profile_result.get("stderr", "")).strip(),
            },
            "profiles": profiles,
        }

    async def run_smoke_check(self, agent_id: str) -> Dict[str, Any]:
        """Execute one no-GLAME-write prompt to verify a profile can run."""

        command = self.build_smoke_check_command(agent_id)
        raw = await self.executor(command, self.config.timeout_seconds)
        exit_code = int(raw.get("exit_code", 1))
        return {
            "agent_id": agent_id,
            "profile": self.profile_for_agent(agent_id),
            "success": exit_code == 0,
            "exit_code": exit_code,
            "output": str(raw.get("stdout", "")).strip(),
            "error": str(raw.get("stderr", "")).strip(),
            "command_preview": command[:5],
        }

    async def run_task(
        self,
        agent_id: str,
        system_prompt: str,
        task_payload: Mapping[str, Any],
    ) -> HermesRunResult:
        """Execute a GLAME task through Hermes and return a normalized result."""

        prompt = self.build_prompt(agent_id, system_prompt, task_payload)
        command = self.build_command(agent_id, prompt)
        raw = await self.executor(command, self.config.timeout_seconds)
        exit_code = int(raw.get("exit_code", 1))
        output = self.clean_output(str(raw.get("stdout", "")).strip())
        error = str(raw.get("stderr", "")).strip()
        return HermesRunResult(
            success=exit_code == 0,
            profile=self.profile_for_agent(agent_id),
            command=command,
            output=output,
            error=error,
            exit_code=exit_code,
        )
