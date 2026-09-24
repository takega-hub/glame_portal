import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class AiCrmAgentBridgeTests(unittest.TestCase):
    def test_normalize_crm_plan_preserves_elena_operating_contract(self):
        from app.services.ai_crm_plan_service import normalize_crm_plan

        plan = normalize_crm_plan({
            "goal": "Вернуть клиентов Ялты",
            "campaign_name": "Ялта CRM",
            "segment": {"segment_id": "seg-1", "segment_name": "Ялта A", "customer_count": 15},
            "scenario": {"channel": "call", "seller_action": "Подготовить видео-подборку"},
            "scripts": {"main_message": "Подготовлю для вас видео-подборку"},
        })

        self.assertEqual(plan["status"], "draft")
        self.assertEqual(plan["approval"]["required_by"], "elena")
        self.assertEqual(plan["segment"]["segment_id"], "seg-1")
        self.assertEqual(plan["scripts"]["main_message"], "Подготовлю для вас видео-подборку")
        self.assertIn("no_mass_send_without_approval", plan["guardrails"])
        self.assertIn("no_comfort_budget_for_crimea", plan["guardrails"])

    def test_extract_crm_plan_from_text_uses_fenced_json(self):
        from app.services.ai_crm_plan_service import extract_crm_plan_from_text

        text = '''Готово.
```json
{"goal":"Допродажа комплектов","campaign_name":"Комплекты","segment":{"segment_name":"14-21 день","customer_count":8},"scripts":{"main_message":"Написать клиентке"}}
```
'''
        plan = extract_crm_plan_from_text(text)

        self.assertEqual(plan["goal"], "Допродажа комплектов")
        self.assertEqual(plan["campaign_name"], "Комплекты")
        self.assertEqual(plan["segment"]["customer_count"], 8)

    def test_agent_interactions_exposes_crm_plan_endpoints_and_operating_context(self):
        source = (ROOT / "backend/app/api/agent_interactions.py").read_text(encoding="utf-8")

        self.assertIn('/tasks/{task_id}/crm/plan', source)
        self.assertIn('/tasks/{task_id}/crm/finalize-plan', source)
        self.assertIn('/tasks/{task_id}/crm/create-seller-tasks', source)
        self.assertIn('GLAME CRM OPERATING CONTEXT', source)
        self.assertIn('no_comfort_budget_for_crimea', source)

    def test_frontend_ai_crm_board_has_plan_actions(self):
        board = (ROOT / "frontend/src/app/ai-marketer/boards/crm/page.tsx").read_text(encoding="utf-8")
        chat = (ROOT / "frontend/src/components/agents/AgentBoardChat.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn('crm/finalize-plan', api)
        self.assertIn('crm/create-seller-tasks', api)
        self.assertIn('CRM-план', chat)
        self.assertIn('Зафиксировать CRM-план', chat)
        self.assertIn('Создать задачи продавцам', chat)
        self.assertIn('crmMode', board)

    def test_ai_crm_exposes_project_topics_panel_contract(self):
        backend = (ROOT / "backend/app/api/agent_interactions.py").read_text(encoding="utf-8")
        board = (ROOT / "frontend/src/app/ai-marketer/boards/crm/page.tsx").read_text(encoding="utf-8")
        chat = (ROOT / "frontend/src/components/agents/AgentBoardChat.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn('/crm/projects', backend)
        self.assertIn('CrmProjectTopicResponse', backend)
        self.assertIn('discussion_result', backend)
        self.assertIn('listCrmProjects', api)
        self.assertIn('CRM-проекты', board)
        self.assertIn('Проект по созвонам', board)
        self.assertIn('Проект по SMS-рассылке', board)
        self.assertIn('projectTopics', board)
        self.assertIn('selectedTaskIdOverride', chat)


if __name__ == "__main__":
    unittest.main()
