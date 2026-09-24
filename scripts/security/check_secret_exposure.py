#!/usr/bin/env python3
"""High-confidence static secret exposure check for tracked files.

The scanner intentionally reports only the finding type, file and line number.
It never prints the matched secret value.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SKIP_PREFIXES = (
    "backend/libs/",
    "frontend/node_modules/",
    "mobile/glame_app/build/",
)
SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".sqlite",
    ".sqlite3",
    ".pyc",
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("telegram_bot_token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "mnemonic_assignment",
        re.compile(
            r"(?i)\b(?:[A-Z0-9_]*MNEMONIC|SEED_PHRASE)\b\s*[:=]\s*['\"]?"
            r"[a-z]+(?:\s+[a-z]+){23}['\"]?"
        ),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    ),
]


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def should_skip(path: str) -> bool:
    return path.startswith(SKIP_PREFIXES) or path.lower().endswith(SKIP_SUFFIXES)


def scan_file(path: str) -> list[dict[str, object]]:
    absolute = PROJECT_ROOT / path
    try:
        text = absolute.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[dict[str, object]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for finding_type, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(
                    {
                        "file": path,
                        "line": line_no,
                        "type": finding_type,
                    }
                )
    return findings


def main() -> int:
    findings: list[dict[str, object]] = []
    checked = 0
    for path in git_ls_files():
        if should_skip(path):
            continue
        checked += 1
        findings.extend(scan_file(path))

    payload = {
        "schema": "glame_secret_exposure_audit_v1",
        "checked": checked,
        "findings": findings,
        "status": "ok" if not findings else "failed",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
