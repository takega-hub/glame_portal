import ast
import unittest
from pathlib import Path


class MarketingAgentContractTests(unittest.TestCase):
    def test_marketing_agent_defines_process_method_required_by_base_agent(self):
        source_path = Path(__file__).resolve().parents[1] / "app" / "agents" / "marketing_agent.py"
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        cls = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "MarketingAgent"
        )

        process_methods = [
            node for node in cls.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "process"
        ]

        self.assertEqual(len(process_methods), 1)


if __name__ == "__main__":
    unittest.main()
