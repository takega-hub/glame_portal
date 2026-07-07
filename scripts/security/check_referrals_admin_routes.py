#!/usr/bin/env python3
"""Verify that referral admin routes are protected by require_admin().

This is a static guard for CryptoGLAME launch readiness. It intentionally
does not import the app or connect to the database.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "backend" / "app" / "api" / "referrals.py"
ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _route_path(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if _name(decorator.func.value) != "router" or decorator.func.attr not in ROUTE_METHODS:
        return None
    if not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _contains_require_admin(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and _name(node.func) == "require_admin":
        return True
    return any(_contains_require_admin(child) for child in ast.iter_child_nodes(node))


def _function_has_admin_dependency(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    candidates: list[ast.AST] = []
    candidates.extend(node.args.defaults)
    candidates.extend(item for item in node.args.kw_defaults if item is not None)
    return any(_contains_require_admin(candidate) for candidate in candidates)


def main() -> int:
    tree = ast.parse(TARGET.read_text(encoding="utf-8"), filename=str(TARGET))
    routes: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        admin_paths = [
            path
            for decorator in node.decorator_list
            if (path := _route_path(decorator)) and path.startswith("/admin")
        ]
        if not admin_paths:
            continue
        protected = _function_has_admin_dependency(node)
        for path in admin_paths:
            item = {
                "path": path,
                "function": node.name,
                "line": node.lineno,
                "protected": protected,
            }
            routes.append(item)
            if not protected:
                missing.append(item)

    payload = {
        "schema": "glame_referrals_admin_route_audit_v1",
        "target": str(TARGET.relative_to(PROJECT_ROOT)),
        "checked": len(routes),
        "missing": missing,
        "status": "ok" if not missing else "failed",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
