import unittest
from pathlib import Path


class AIMarketerAgentRegistryApiTests(unittest.TestCase):
    def test_runtime_agent_registry_route_is_registered(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/api/ai_marketer.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/agents/runtime")', source)
        self.assertIn("get_marketing_agent_runtime_registry", source)

    def test_hermes_readiness_route_is_registered_as_read_only(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/api/ai_marketer.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/agents/hermes/readiness")', source)
        self.assertIn("HermesAgentRuntime", source)
        self.assertIn("check_readiness", source)
        self.assertIn('readiness["runtime_status"] = agent_runtime_status_from_env()', source)

    def test_hermes_smoke_check_route_is_registered_without_glame_writes(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/api/ai_marketer.py").read_text(encoding="utf-8")

        self.assertIn('@router.post("/agents/hermes/{agent_id}/smoke-check")', source)
        self.assertIn("run_smoke_check", source)

    def test_agent_runtime_status_route_exposes_effective_feature_flag(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/api/ai_marketer.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/agents/runtime/status")', source)
        self.assertIn("agent_runtime_status_from_env", source)


if __name__ == "__main__":

    unittest.main()
