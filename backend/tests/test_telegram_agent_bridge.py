import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class TelegramAgentBridgeTests(unittest.TestCase):
    def test_route_selector_defaults_crm_messages_to_ai_crm_board(self):
        from app.services.telegram_agent_bridge_service import resolve_telegram_agent_route

        route = resolve_telegram_agent_route("Елена: собери CRM сегмент Ялта и скрипт звонка")

        self.assertEqual(route["board_id"], "crm")
        self.assertEqual(route["target_agent"], "crm-agent")
        self.assertEqual(route["task_type"], "crm_telegram_dialog")

    def test_task_payload_preserves_telegram_as_channel_not_source_of_truth(self):
        from app.services.telegram_agent_bridge_service import build_telegram_task_payload

        payload = build_telegram_task_payload(
            board_id="crm",
            target_agent="crm-agent",
            task_type="crm_telegram_dialog",
            chat_id="315851436",
            from_user="Elena",
            message="Подбери сегмент и напиши скрипты",
            topic_id="crm",
        )

        self.assertEqual(payload["task_context"]["board"], "crm")
        self.assertEqual(payload["task_context"]["platform_bridge"], "telegram")
        self.assertEqual(payload["task_context"]["source_of_truth"], "glame_platform")
        self.assertIn("telegram:315851436:crm", payload["task_context"]["idempotency_key"])
        self.assertIn("Telegram CRM", payload["input_data"]["title"])

    def test_api_route_registered_and_protected_by_bridge_secret(self):
        api = (ROOT / "backend/app/api/telegram_agent_bridge.py").read_text(encoding="utf-8")
        main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

        self.assertIn('/telegram/agent/message', api)
        self.assertIn('TELEGRAM_AGENT_BRIDGE_SECRET', api)
        self.assertIn('agent_interaction_logs', api)
        self.assertIn('telegram_agent_bridge.router', main)


if __name__ == "__main__":
    unittest.main()
