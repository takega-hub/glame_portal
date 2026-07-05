#!/usr/bin/env python3
"""Host-side smoke check for GLAME Hermes runtime wiring."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env  # noqa: E402


def load_env_file(path: Path) -> None:
    """Load a simple systemd-style EnvironmentFile without printing values."""

    if not path.exists():
        raise SystemExit(f"env file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        default=None,
        help="Optional systemd-style env file to load before checking Hermes runtime.",
    )
    parser.add_argument(
        "--dry-run-agent",
        default=None,
        help="Optionally run one no-GLAME-write Hermes prompt for this agent id.",
    )
    args = parser.parse_args()

    if args.env_file:
        load_env_file(Path(args.env_file))

    runtime = HermesAgentRuntime(hermes_runtime_config_from_env())
    payload = await runtime.check_readiness()
    if args.dry_run_agent:
        payload["dry_run"] = await runtime.run_smoke_check(args.dry_run_agent)

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    ok = payload["binary"]["available"] and payload["profile_list"]["available"]
    ok = ok and all(item["exists"] for item in payload["profiles"].values())
    if args.dry_run_agent:
        ok = ok and payload["dry_run"]["success"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
