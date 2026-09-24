#!/usr/bin/env python3
"""Build a local CryptoGLAME launch evidence packet without secret values."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLM_POLICY_DIR = PROJECT_ROOT / "backend" / "static" / "glm_policy"

POLICY_DOCUMENTS = [
    "token-policy.md",
    "risk-disclosure.md",
    "bridge-rules.md",
    "emission-policy.md",
    "faq.md",
    "operator-runbook.md",
    "production-escalation-policy.md",
    "production-signer-contract.md",
    "security-review-checklist.md",
    "legal-accounting-approval.md",
    "treasury-approval.md",
    "launch-approval-packet.md",
    "p2p-marketplace-approval-packet.md",
    "exchange-desk-policy.md",
    "jetton-metadata-mainnet-v2.json",
]


def run_command(command: list[str], *, cwd: Path = PROJECT_ROOT) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "command": " ".join(command),
        "cwd": str(cwd.relative_to(PROJECT_ROOT)) if cwd != PROJECT_ROOT else ".",
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_fingerprints() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for filename in POLICY_DOCUMENTS:
        path = GLM_POLICY_DIR / filename
        documents.append(
            {
                "file": str(path.relative_to(PROJECT_ROOT)),
                "exists": path.exists(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size if path.exists() else None,
            }
        )
    return documents


def approval_state() -> dict[str, Any]:
    path = GLM_POLICY_DIR / "production-approvals.json"
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except json.JSONDecodeError as error:
            return {"exists": True, "valid_json": False, "error": str(error)}
    return {
        "exists": path.exists(),
        "valid_json": True,
        "legal_approved": bool(payload.get("legal_approved")),
        "security_approved": bool(payload.get("security_approved")),
        "treasury_approved": bool(payload.get("treasury_approved")),
        "updated_at": payload.get("updated_at"),
        "comment_present": bool(payload.get("comment")),
        "updated_by_present": bool(payload.get("updated_by")),
    }


def git_state() -> dict[str, Any]:
    head = run_command(["git", "rev-parse", "HEAD"])
    branch = run_command(["git", "branch", "--show-current"])
    status = run_command(["git", "status", "--short"])
    return {
        "head": head["stdout"] if head["ok"] else None,
        "branch": branch["stdout"] if branch["ok"] else None,
        "dirty": bool(status["stdout"]),
        "status_short": status["stdout"].splitlines() if status["stdout"] else [],
    }


def launch_checks(skip_live: bool) -> dict[str, Any]:
    command = ["python3", "scripts/security/run_crypto_glame_launch_checks.py"]
    if skip_live:
        command.append("--skip-live")
    result = run_command(command)
    payload = parse_json(result["stdout"])
    return {
        "ok": result["ok"],
        "returncode": result["returncode"],
        "payload": payload,
        "stderr_tail": result["stderr"][-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live public URL checks in the nested launch-check runner.",
    )
    parser.add_argument(
        "--write",
        type=Path,
        help="Optional path to write the JSON evidence packet.",
    )
    parser.add_argument(
        "--allow-public-static",
        action="store_true",
        help="Allow writing under backend/static. This is discouraged for approval evidence.",
    )
    args = parser.parse_args()

    checks = launch_checks(skip_live=args.skip_live)
    packet = {
        "schema": "glame_crypto_launch_evidence_packet_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ok": bool(checks.get("ok")),
        "git": git_state(),
        "approvals": approval_state(),
        "policy_documents": document_fingerprints(),
        "checks": checks,
        "manual_evidence_required": [
            "admin /admin/crypto readiness screenshot",
            "production signer health/preflight screenshot",
            "bridge reconciliation CSV",
            "treasury turnover CSV",
            "mainnet points_to_glm tx hash and 1C movement evidence",
            "mainnet glm_to_points tx hash and 1C movement evidence",
            "GLM Store checkout/fulfillment or checkout/refund evidence",
            "Tonkeeper asset-list PR review/merge/propagation evidence",
        ],
    }

    output = json.dumps(packet, ensure_ascii=False, indent=2)
    print(output)

    if args.write:
        target = args.write if args.write.is_absolute() else PROJECT_ROOT / args.write
        try:
            target.relative_to(PROJECT_ROOT / "backend" / "static")
        except ValueError:
            pass
        else:
            if not args.allow_public_static:
                print(
                    "Refusing to write launch evidence under backend/static without --allow-public-static.",
                    file=sys.stderr,
                )
                return 2
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")

    return 0 if packet["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
