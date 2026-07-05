import unittest

from app.services.agent_execution_dispatcher import AgentExecutionDispatcher


class AgentExecutionDispatcherTests(unittest.TestCase):
    def test_resolves_canonical_aliases_to_current_handlers(self):
        dispatcher = AgentExecutionDispatcher()

        brand = dispatcher.resolve("brand-media-agent")
        self.assertEqual(brand.canonical_agent_id, "brand-media-agent")
        self.assertEqual(brand.execution_agent_id, "content-agent")
        self.assertEqual(brand.process_handler, "content")
        self.assertTrue(brand.supports_task_process)

        crm = dispatcher.resolve("communication-agent")
        self.assertEqual(crm.canonical_agent_id, "crm-agent")
        self.assertEqual(crm.execution_agent_id, "communication-agent")

    def test_rejects_chat_only_agents_for_task_process(self):
        dispatcher = AgentExecutionDispatcher()

        with self.assertRaises(ValueError) as ctx:
            dispatcher.require_process_handler("pr-partnerships-agent")

        self.assertIn("task chat", str(ctx.exception))

    def test_inventory_technical_agents_are_supported_during_migration(self):
        dispatcher = AgentExecutionDispatcher()

        self.assertEqual(
            dispatcher.resolve_process_agent_id("inventory-procurement-agent"),
            "inventory-procurement-agent",
        )
        self.assertEqual(
            dispatcher.resolve_process_agent_id("assortment-agent"),
            "marketing-inventory-agent",
        )

    def test_process_status_gate_allows_only_approved_queue_processing_or_completed(self):
        dispatcher = AgentExecutionDispatcher()

        for status in ["approved", "queued", "processing", "completed"]:
            dispatcher.require_process_status_allowed(status)

        for status in ["pending", "validating", "validated", "pending_approval", "rejected", "cancelled", "failed", "deleted"]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    dispatcher.require_process_status_allowed(status)


if __name__ == "__main__":
    unittest.main()
