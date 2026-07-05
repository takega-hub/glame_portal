import ast
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "app" / "api" / "knowledge.py"


ROUTE_TO_PERMISSION = {
    "debug_env": "knowledge_read_access",
    "search_knowledge": "knowledge_read_access",
    "get_knowledge_stats": "knowledge_read_access",
    "check_duplicates": "knowledge_read_access",
    "get_knowledge_documents": "knowledge_read_access",
    "get_knowledge_document": "knowledge_read_access",
    "upload_knowledge": "knowledge_upload_access",
    "upload_knowledge_from_file": "knowledge_upload_access",
    "upload_knowledge_batch": "knowledge_upload_access",
    "sync_products_to_knowledge": "knowledge_upload_access",
    "change_document_collection": "knowledge_manage_access",
    "replace_knowledge_document": "knowledge_manage_access",
    "delete_knowledge_document": "knowledge_delete_access",
    "clear_knowledge_collection": "knowledge_delete_access",
}

MUTATING_ROUTES = {
    "upload_knowledge",
    "upload_knowledge_from_file",
    "upload_knowledge_batch",
    "sync_products_to_knowledge",
    "change_document_collection",
    "replace_knowledge_document",
    "delete_knowledge_document",
    "clear_knowledge_collection",
}


def _module():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _functions():
    return {
        node.name: node
        for node in _module().body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _argument_defaults(fn):
    positional = list(fn.args.args)
    defaults = [None] * (len(positional) - len(fn.args.defaults)) + list(fn.args.defaults)
    yield from zip(positional, defaults)
    yield from zip(fn.args.kwonlyargs, fn.args.kw_defaults)


def _depends_name(default):
    if not isinstance(default, ast.Call):
        return None
    if not isinstance(default.func, ast.Name) or default.func.id != "Depends":
        return None
    if not default.args:
        return None
    dep = default.args[0]
    if isinstance(dep, ast.Name):
        return dep.id
    return None


class KnowledgeApiSecurityTests(unittest.TestCase):
    def test_every_knowledge_route_requires_operation_specific_access_dependency(self):
        functions = _functions()
        missing = []
        for route_name, dependency_name in ROUTE_TO_PERMISSION.items():
            route = functions[route_name]
            dependency_names = [_depends_name(default) for _, default in _argument_defaults(route) if default is not None]
            if dependency_name not in dependency_names:
                missing.append(f"{route_name}: expected Depends({dependency_name})")
        self.assertFalse(missing, "\n".join(missing))

    def test_mutating_knowledge_routes_emit_audit_log(self):
        functions = _functions()
        missing = []
        for route_name in MUTATING_ROUTES:
            route = functions[route_name]
            calls = [node for node in ast.walk(route) if isinstance(node, ast.Call)]
            has_audit = any(isinstance(call.func, ast.Name) and call.func.id == "_audit_knowledge_action" for call in calls)
            if not has_audit:
                missing.append(route_name)
        self.assertFalse(missing, "mutating routes without _audit_knowledge_action: " + ", ".join(sorted(missing)))


if __name__ == "__main__":
    unittest.main()
