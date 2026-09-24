#!/usr/bin/env python3
"""Run local CryptoGLAME launch-readiness checks and print one JSON report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    parse_json: bool = False,
) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    payload: dict[str, Any] | None = None
    if parse_json and stdout:
        payload = parse_json_payload(stdout)

    return {
        "name": name,
        "command": " ".join(command),
        "cwd": str(cwd.relative_to(PROJECT_ROOT)) if cwd != PROJECT_ROOT else ".",
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "payload": payload,
        "stdout_tail": stdout[-4000:] if not payload else "",
        "stderr_tail": stderr[-4000:],
    }


def parse_json_payload(output: str) -> dict[str, Any] | None:
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            payload = json.loads(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live public URL checks for the Tonkeeper asset package.",
    )
    parser.add_argument(
        "--write",
        type=Path,
        help="Optional path to write the JSON report.",
    )
    args = parser.parse_args()

    checks: list[dict[str, Any]] = [
        run_command(
            "secret_exposure",
            ["python3", "scripts/security/check_secret_exposure.py"],
            parse_json=True,
        ),
        run_command(
            "referrals_admin_routes",
            ["python3", "scripts/security/check_referrals_admin_routes.py"],
            parse_json=True,
        ),
        run_command(
            "security_scripts_py_compile",
            [
                "python3",
                "-m",
                "py_compile",
                "scripts/security/check_secret_exposure.py",
                "scripts/security/check_referrals_admin_routes.py",
                "scripts/security/build_crypto_glame_evidence_packet.py",
                "scripts/security/run_crypto_glame_launch_checks.py",
            ],
        ),
        run_command(
            "git_diff_check",
            ["git", "diff", "--check"],
        ),
        run_command(
            "ton_assets_package",
            ["npm", "run", "validate:ton-assets"],
            cwd=PROJECT_ROOT / "contracts/ton/glm-jetton",
            parse_json=True,
        ),
    ]

    if not args.skip_live:
        checks.append(
            run_command(
                "ton_assets_package_live",
                ["npm", "run", "validate:ton-assets:live"],
                cwd=PROJECT_ROOT / "contracts/ton/glm-jetton",
                parse_json=True,
            )
        )

    report = {
        "schema": "glame_crypto_launch_checks_v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }

    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)

    if args.write:
        target = args.write if args.write.is_absolute() else PROJECT_ROOT / args.write
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
