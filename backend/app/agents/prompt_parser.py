"""Utilities for loading GLAME AI agent system prompts from markdown docs."""
from __future__ import annotations

import re
from typing import Dict, List

from app.agents.contracts import DOC_PROMPT_TITLE_TO_AGENT_ID


def parse_agent_prompts_from_markdown(text: str, docs_path: str) -> List[Dict[str, str]]:
    """Parse default agent prompts from legacy v1 and canonical v1_2 docs."""
    parsed: List[Dict[str, str]] = []

    # Legacy v1 format: sections contain explicit "**Agent Type:** `...`" and code blocks.
    sections = re.split(r"\n##\s+", "\n" + text)
    for section in sections:
        agent_match = re.search(r"\*\*Agent Type:\*\*\s*`([^`]+)`", section)
        if not agent_match:
            continue
        code_blocks = re.findall(r"```(?:text)?\n(.*?)```", section, flags=re.S)
        if not code_blocks:
            continue
        agent_type = agent_match.group(1).strip()
        title = section.splitlines()[0].strip("# ").strip() or agent_type
        parsed.append({
            "agent_type": agent_type,
            "name": f"{title} default prompt",
            "description": f"Seeded from {docs_path}",
            "system_prompt": code_blocks[0].strip(),
        })

    # v1_2 format: top-level "# N. AI NAME — SYSTEM PROMPT" sections without code fences.
    if not parsed:
        global_match = re.search(
            r"# 0\. GLOBAL INHERITANCE RULES FOR ALL AGENTS\n(.*?)(?=\n# 1\. AI MARKETING DIRECTOR)",
            text,
            flags=re.S,
        )
        global_rules = global_match.group(0).strip() if global_match else ""
        section_matches = list(
            re.finditer(
                r"^#\s+\d+\.\s+(AI [^\n]+?)\s+—\s+SYSTEM PROMPT\s*$",
                text,
                flags=re.M,
            )
        )
        for idx, match in enumerate(section_matches):
            title = match.group(1).strip()
            agent_type = DOC_PROMPT_TITLE_TO_AGENT_ID.get(title.upper())
            if not agent_type:
                continue
            start = match.start()
            end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(text)
            section_text = text[start:end].strip()
            prompt_text = f"{global_rules}\n\n{section_text}".strip() if global_rules else section_text
            parsed.append({
                "agent_type": agent_type,
                "name": f"{title} system prompt",
                "description": f"Seeded from {docs_path}",
                "system_prompt": prompt_text,
            })

    return parsed
