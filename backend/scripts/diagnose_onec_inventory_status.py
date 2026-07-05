#!/usr/bin/env python3
"""Diagnose GLAME 1C sync status and inventory analytics consistency.

Checks the production API contract without printing credentials:
- /api/admin/1c/sync/status must not return 500
- if /api/inventory/dashboard reports stock.total_stock > 0, analytics health
  must not be no_data and /api/analytics/inventory/analysis must not be total=0

This script reuses /workspace/tools/glame_api.py when available so it runs in the
same host/container environments as the Hermes cron wrappers.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


CANDIDATE_HELPERS = [
    Path("/home/glameAI/tools/glame_api.py"),
    Path("/workspace/tools/glame_api.py"),
]


class DiagnosticError(RuntimeError):
    pass


def load_glame_api():
    for helper in CANDIDATE_HELPERS:
        if helper.exists():
            spec = importlib.util.spec_from_file_location("glame_api", helper)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.load_dotenv()
                return module
    raise DiagnosticError("glame_api.py helper not found in host/container paths")


def api_get(glame_api: Any, path: str) -> tuple[int, Any]:
    from urllib import error, request

    try:
        env = glame_api.require_env(["GLAME_API_BASE_URL"])
        token = glame_api.get_access_token(env["GLAME_API_BASE_URL"], 20)
        url = glame_api.build_url(env["GLAME_API_BASE_URL"], path, [])
        req = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "glame-hermes-diagnostic/0.1",
            },
            method="GET",
        )
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body) if body else None
            except json.JSONDecodeError:
                data = body
            return int(response.status), data
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = body
        return int(exc.code), data
    except Exception as exc:  # noqa: BLE001 - diagnostics should include endpoint failures
        return 0, {"error": str(exc)}


def fail(message: str, payload: Any | None = None) -> None:
    print(json.dumps({"status": "fail", "message": message, "payload": payload}, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def main() -> int:
    glame_api = load_glame_api()

    checks: dict[str, Any] = {}
    status_code, sync_status = api_get(glame_api, "/api/admin/1c/sync/status")
    checks["sync_status"] = {"http": status_code, "body": sync_status}
    if status_code >= 500 or (isinstance(sync_status, dict) and "Boolean value of this clause" in str(sync_status)):
        fail("/api/admin/1c/sync/status is broken", checks)

    dash_code, dashboard = api_get(glame_api, "/api/inventory/dashboard")
    checks["dashboard"] = {"http": dash_code, "body": dashboard}
    total_stock = 0.0
    if dash_code == 200 and isinstance(dashboard, dict):
        total_stock = float(((dashboard.get("stock") or {}).get("total_stock")) or 0.0)

    health_code, health = api_get(glame_api, "/api/analytics/inventory/health-score")
    analysis_code, analysis = api_get(glame_api, "/api/analytics/inventory/analysis?limit=5")
    checks["health_score"] = {"http": health_code, "body": health}
    checks["analysis"] = {"http": analysis_code, "body": analysis}

    if total_stock > 0:
        if health_code != 200 or not isinstance(health, dict) or health.get("status") == "no_data":
            fail("inventory health-score is no_data while dashboard stock exists", checks)
        if analysis_code != 200 or not isinstance(analysis, dict) or int(analysis.get("total") or 0) == 0:
            fail("inventory analysis is empty while dashboard stock exists", checks)

    print(json.dumps({"status": "ok", "checks": checks}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
