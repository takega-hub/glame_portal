import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.contracts import (
    CANONICAL_AGENT_IDS,
    MARKETING_AGENT_REGISTRY,
    AgentCommunicationEnvelope,
    AgentPriority,
    BusinessStage,
    CommunicationType,
    board_aliases,
    canonical_agent_id,
    execution_agent_id,
    prompt_agent_id,
)
from app.agents.prompt_parser import parse_agent_prompts_from_markdown
from app.agents.runtime_registry import (
    get_runtime_agent_registry,
    get_runtime_agent_spec,
    supported_process_agent_ids,
)
from app.agents.agent_registry import get_marketing_agent_runtime_registry


class AgentContractsTests(unittest.TestCase):
    def test_registry_contains_eight_canonical_agents(self):
        self.assertEqual(len(MARKETING_AGENT_REGISTRY), 8)
        self.assertEqual(len(CANONICAL_AGENT_IDS), 8)
        self.assertEqual(len(set(CANONICAL_AGENT_IDS)), 8)
        self.assertIn("director-agent", CANONICAL_AGENT_IDS)
        self.assertIn("brand-media-agent", CANONICAL_AGENT_IDS)
        self.assertIn("crm-agent", CANONICAL_AGENT_IDS)
        self.assertIn("assortment-agent", CANONICAL_AGENT_IDS)

    def test_alias_normalization_and_execution_prompt_routing(self):
        self.assertEqual(canonical_agent_id("content-agent"), "brand-media-agent")
        self.assertEqual(canonical_agent_id("communication-agent"), "crm-agent")
        self.assertEqual(execution_agent_id("brand-media-agent"), "content-agent")
        self.assertEqual(execution_agent_id("crm-agent"), "communication-agent")
        self.assertEqual(prompt_agent_id("content-agent"), "brand-media-agent")
        self.assertEqual(prompt_agent_id("marketing-inventory-agent"), "assortment-agent")
        self.assertIn("brand-media-agent", board_aliases("content"))

    def test_agent_communication_envelope_normalizes_agents(self):
        envelope = AgentCommunicationEnvelope(
            from_agent="marketing-director",
            to_agent="content-agent",
            type=CommunicationType.TASK_ASSIGNMENT,
            priority=AgentPriority.P1,
            task="Prepare weekly content package",
            expected_output="Content package",
            status=BusinessStage.BRIEFED,
        ).normalized()
        self.assertEqual(envelope.from_agent, "director-agent")
        self.assertEqual(envelope.to_agent, "brand-media-agent")

    def test_runtime_registry_covers_all_canonical_agents_with_execution_metadata(self):
        registry = get_runtime_agent_registry()

        self.assertEqual(set(registry.keys()), set(CANONICAL_AGENT_IDS))
        brand = registry["brand-media-agent"]
        self.assertEqual(brand.board_id, "content")
        self.assertEqual(brand.prompt_agent_id, "brand-media-agent")
        self.assertEqual(brand.execution_agent_id, "content-agent")
        self.assertEqual(brand.process_handler, "content")
        self.assertTrue(brand.supports_task_process)

        pr = registry["pr-partnerships-agent"]
        self.assertEqual(pr.board_id, "partnership")
        self.assertEqual(pr.process_handler, "task_chat_only")
        self.assertFalse(pr.supports_task_process)

        assortment = registry["assortment-agent"]
        self.assertEqual(assortment.execution_agent_id, "marketing-inventory-agent")
        self.assertEqual(assortment.process_handler, "assortment_matrix")
        self.assertTrue(assortment.supports_task_process)

    def test_runtime_registry_resolves_aliases_and_supported_process_agents(self):
        self.assertEqual(get_runtime_agent_spec("content-agent").canonical_agent_id, "brand-media-agent")
        self.assertEqual(get_runtime_agent_spec("communication-agent").canonical_agent_id, "crm-agent")
        self.assertEqual(get_runtime_agent_spec("marketing-inventory-agent").canonical_agent_id, "assortment-agent")

        process_ids = supported_process_agent_ids()
        self.assertIn("content-agent", process_ids)
        self.assertIn("communication-agent", process_ids)
        self.assertIn("analytics-agent", process_ids)
        self.assertIn("marketing-inventory-agent", process_ids)
        self.assertNotIn("pr-partnerships-agent", process_ids)
        self.assertNotIn("traffic-growth-agent", process_ids)

    def test_public_agent_registry_exposes_runtime_metadata(self):
        registry = get_marketing_agent_runtime_registry()
        content = next(item for item in registry if item["id"] == "brand-media-agent")

        self.assertEqual(content["board_id"], "content")
        self.assertEqual(content["execution_agent_id"], "content-agent")
        self.assertEqual(content["process_handler"], "content")
        self.assertEqual(content["hermes_profile"], "glame-brand-media")
        self.assertTrue(content["supports_task_process"])

    def test_public_agent_registry_reflects_hermes_profile_env_overrides(self):
        with patch.dict("os.environ", {"GLAME_HERMES_PROFILE_CRM_AGENT": "glame-crm-staging"}):
            registry = get_marketing_agent_runtime_registry()

        crm = next(item for item in registry if item["id"] == "crm-agent")
        self.assertEqual(crm["hermes_profile"], "glame-crm-staging")


class AgentPromptParserTests(unittest.TestCase):
    def test_v1_2_prompt_document_parses_all_canonical_agents(self):
        root = Path(__file__).resolve().parents[2]
        docs_path = "docs/admin/GLAME_AI_Agent_System_Prompts_v1_2.md"
        text = (root / docs_path).read_text(encoding="utf-8")

        parsed = parse_agent_prompts_from_markdown(text, docs_path)
        agent_ids = [item["agent_type"] for item in parsed]

        self.assertEqual(len(parsed), 8)
        self.assertEqual(set(agent_ids), set(CANONICAL_AGENT_IDS))
        self.assertEqual(len(agent_ids), len(set(agent_ids)))

        for item in parsed:
            self.assertTrue(item["system_prompt"].startswith("# 0. GLOBAL INHERITANCE RULES"))
            self.assertIn("Seeded from docs/admin/GLAME_AI_Agent_System_Prompts_v1_2.md", item["description"])

    def test_legacy_prompt_format_is_still_supported(self):
        text = """
## Content Agent
**Agent Type:** `content-agent`
```text
Legacy prompt body
```
"""
        parsed = parse_agent_prompts_from_markdown(text, "legacy.md")
        self.assertEqual(parsed, [{
            "agent_type": "content-agent",
            "name": "Content Agent default prompt",
            "description": "Seeded from legacy.md",
            "system_prompt": "Legacy prompt body",
        }])


if __name__ == "__main__":
    unittest.main()
