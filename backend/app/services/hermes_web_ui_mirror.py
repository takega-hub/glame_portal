"""Mirror GLAME agent chats into Hermes Web UI sessions.

Hermes CLI runs write to the profile state database, while Hermes Web UI keeps
its visible chat list in its own SQLite database. This adapter makes GLAME's
director chat visible in that UI without making the main GLAME request depend
on the Web UI being available.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from app.services.hermes_agent_runtime import DEFAULT_HERMES_PROFILE_BY_AGENT_ID


logger = logging.getLogger(__name__)

DEFAULT_WEB_UI_DB = "/root/.hermes-web-ui/hermes-web-ui.db"


def _web_ui_db_path() -> Path:
    return Path(os.getenv("HERMES_WEB_UI_DB", DEFAULT_WEB_UI_DB)).expanduser()


def _session_id_for_glame(agent_id: str, glame_session_id: Optional[str], user_id: Optional[str]) -> str:
    seed = f"{agent_id}:{glame_session_id or user_id or 'default'}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:18]
    return f"glame-{agent_id}-{digest}"


def _trim_title(text: str, fallback: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return fallback
    return compact[:96]


def mirror_glame_turn_to_hermes_web_ui(
    *,
    agent_id: str,
    profile: Optional[str] = None,
    user_id: Optional[str],
    session_id: Optional[str],
    title: Optional[str],
    user_message: str,
    assistant_response: str,
    model: Optional[str] = None,
) -> None:
    """Best-effort mirror of a GLAME chat turn into Hermes Web UI."""

    db_path = _web_ui_db_path()
    if not db_path.exists():
        return

    profile = profile or DEFAULT_HERMES_PROFILE_BY_AGENT_ID.get(agent_id, "glame-agent-worker")
    web_session_id = _session_id_for_glame(agent_id, session_id, user_id)
    now = int(time.time())
    title_text = _trim_title(title or user_message, "GLAME Agent")
    preview = _trim_title(assistant_response, "")

    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute(
                """
                INSERT INTO sessions (
                    id, profile, source, user_id, model, provider, title,
                    started_at, ended_at, end_reason, message_count,
                    tool_call_count, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, reasoning_tokens,
                    estimated_cost_usd, cost_status, preview, last_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, 0, 0, 0, 0, 0, 0, 0, '', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile=excluded.profile,
                    model=excluded.model,
                    provider=excluded.provider,
                    title=COALESCE(NULLIF(sessions.title, ''), excluded.title),
                    preview=excluded.preview,
                    last_active=excluded.last_active
                """,
                (
                    web_session_id,
                    profile,
                    "cli",
                    user_id,
                    model or "",
                    "glame-platform",
                    title_text,
                    now,
                    preview,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (web_session_id, "user", user_message or "", now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (web_session_id, "assistant", assistant_response or "", now),
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (web_session_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE sessions SET message_count = ?, last_active = ?, preview = ? WHERE id = ?",
                (int(count or 0), now, preview, web_session_id),
            )
    except Exception:
        logger.exception("Failed to mirror GLAME chat turn to Hermes Web UI")


def mirror_director_turn_to_hermes_web_ui(
    *,
    user_id: Optional[str],
    session_id: Optional[str],
    user_message: str,
    director_response: str,
    model: Optional[str] = None,
) -> None:
    """Best-effort mirror of a GLAME director chat turn into Hermes Web UI."""

    mirror_glame_turn_to_hermes_web_ui(
        agent_id="director-agent",
        user_id=user_id,
        session_id=session_id,
        title=None,
        user_message=user_message,
        assistant_response=director_response,
        model=model,
    )


def mirror_agent_task_turn_to_hermes_web_ui(
    *,
    agent_id: str,
    task_id: str,
    task_title: str,
    user_message: str,
    assistant_response: str,
    model: Optional[str] = None,
) -> None:
    """Mirror a GLAME task chat as a named Hermes Web UI session."""

    mirror_glame_turn_to_hermes_web_ui(
        agent_id=agent_id,
        user_id=None,
        session_id=task_id,
        title=task_title,
        user_message=user_message,
        assistant_response=assistant_response,
        model=model,
    )
