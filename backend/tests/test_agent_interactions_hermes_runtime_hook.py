import unittest
from pathlib import Path


class AgentInteractionsHermesRuntimeHookTests(unittest.TestCase):
    def test_process_endpoint_has_feature_flagged_hermes_runtime_hook_before_legacy_handlers(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "backend/app/api/agent_interactions.py").read_text(encoding="utf-8")

        self.assertIn("HermesTaskExecutionService", source)
        self.assertIn("hermes_task_service = HermesTaskExecutionService()", source)
        self.assertIn("if await hermes_task_service.execute(task, db):", source)
        self.assertLess(
            source.index("if await hermes_task_service.execute(task, db):"),
            source.index("if execution_agent == \"director-agent\":"),
        )


if __name__ == "__main__":
    unittest.main()
