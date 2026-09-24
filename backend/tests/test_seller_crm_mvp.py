import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class SellerCrmMvpTests(unittest.TestCase):
    def test_result_validation_requires_comment_and_next_date_for_postpone(self):
        from app.services.crm_task_validation import validate_crm_task_result

        with self.assertRaises(ValueError):
            validate_crm_task_result("sent_no_reply", "", None)

        with self.assertRaises(ValueError):
            validate_crm_task_result("postpone", "Клиент попросила позже", None)

        status = validate_crm_task_result("postpone", "Клиент попросила позже", "2026-07-24")
        self.assertEqual(status, "postponed")

    def test_terminal_outcomes_map_to_terminal_statuses(self):
        from app.services.crm_task_validation import validate_crm_task_result

        self.assertEqual(validate_crm_task_result("not_relevant", "Неактуально", None), "not_relevant")
        self.assertEqual(validate_crm_task_result("do_not_disturb", "Не беспокоить", None), "do_not_disturb")
        self.assertEqual(validate_crm_task_result("quality_complaint", "Пожаловалась на покрытие", None), "quality_complaint")
        self.assertEqual(validate_crm_task_result("sale", "Продажа после видео", None), "worked")

    def test_routes_and_pages_are_registered(self):
        main_source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        api_source = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        navigation_source = (ROOT / "frontend/src/config/navigation.ts").read_text(encoding="utf-8")

        self.assertIn("seller_crm", main_source)
        self.assertIn("admin_crm_tasks", main_source)
        self.assertIn("/api/seller/crm/tasks", api_source)
        self.assertIn("/api/admin/crm/tasks", api_source)
        self.assertIn("/api/admin/crm/tasks/analytics", api_source)
        self.assertIn("/profile/sellers/crm", navigation_source)

    def test_crm_task_model_defines_idempotency_and_event_history(self):
        model_source = (ROOT / "backend/app/models/crm_task.py").read_text(encoding="utf-8")

        self.assertIn("class CrmTask", model_source)
        self.assertIn("class CrmTaskEvent", model_source)
        self.assertIn("source_idempotency_key", model_source)
        self.assertIn("crm_task_events", model_source)
        self.assertIn("assigned_seller_external_id", model_source)

    def test_crm_result_payload_matches_customer_messages_tab_contract(self):
        from app.services.crm_task_validation import build_crm_customer_message_payload

        payload = build_crm_customer_message_payload(
            task_id="task-1",
            status="worked",
            seller_outcome="photo_video_sent",
            seller_comment="Отправили видео, клиентка выбирает",
            next_action_date="2026-07-24",
            crm_group="B. Личное сообщение",
            reason="Повторный контакт",
            seller_action="Отправить подборку",
            script_key="yalta_remote_video",
            store_name="GLAME Ялта",
            seller_name="Мария",
            work_date="2026-07-21",
            campaign_id="crm-july",
            campaign_name="Июльская CRM",
        )

        self.assertEqual(payload["source"], "seller_crm_task")
        self.assertEqual(payload["message_kind"], "crm_call")
        self.assertEqual(payload["crm_task_id"], "task-1")
        self.assertEqual(payload["seller_outcome"], "photo_video_sent")
        self.assertEqual(payload["comment"], "Отправили видео, клиентка выбирает")
        self.assertEqual(payload["interaction_reason"], "Повторный контакт")
        self.assertEqual(payload["interacted_by"], "Мария")

    def test_crm_sql_migration_exists_and_runtime_routes_do_not_bootstrap_schema(self):
        sql_source = (ROOT / "backend/sql/create_crm_tasks.sql").read_text(encoding="utf-8")
        migration_script = (ROOT / "backend/apply_crm_tasks_migration.py").read_text(encoding="utf-8")
        seller_api = (ROOT / "backend/app/api/seller_crm.py").read_text(encoding="utf-8")
        admin_api = (ROOT / "backend/app/api/admin/crm_tasks.py").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS crm_tasks", sql_source)
        self.assertIn("CREATE TABLE IF NOT EXISTS crm_task_events", sql_source)
        self.assertIn("source_idempotency_key", sql_source)
        self.assertIn("create_crm_tasks.sql", migration_script)
        self.assertIn("redacted_db_target", migration_script)
        self.assertNotIn("ensure_tables", seller_api)
        self.assertNotIn("ensure_tables", admin_api)

    def test_crm_service_writes_result_to_customer_messages(self):
        service_source = (ROOT / "backend/app/services/crm_task_service.py").read_text(encoding="utf-8")

        self.assertIn("_record_customer_message", service_source)
        self.assertIn("CustomerMessage", service_source)
        self.assertIn("event_type=\"crm_call\"", service_source)
        self.assertIn("message_kind", service_source)

    def test_crm_assignment_allows_store_managers(self):
        service_source = (ROOT / "backend/app/services/crm_task_service.py").read_text(encoding="utf-8")
        admin_api = (ROOT / "backend/app/api/admin/crm_tasks.py").read_text(encoding="utf-8")

        self.assertIn('CRM_ASSIGNEE_ROLES = {"seller", "manager"}', service_source)
        self.assertIn('CRM_ASSIGNEE_ROLES = ("seller", "manager")', admin_api)
        self.assertIn("User.role.in_(CRM_ASSIGNEE_ROLES)", service_source)
        self.assertIn("User.role.in_(CRM_ASSIGNEE_ROLES)", admin_api)

    def test_crm_campaign_analytics_contract_is_exposed(self):
        schemas_source = (ROOT / "backend/app/schemas/crm_tasks.py").read_text(encoding="utf-8")
        service_source = (ROOT / "backend/app/services/crm_task_service.py").read_text(encoding="utf-8")
        admin_api = (ROOT / "backend/app/api/admin/crm_tasks.py").read_text(encoding="utf-8")
        frontend_source = (ROOT / "frontend/src/components/admin/AdminCrmTasksPage.tsx").read_text(encoding="utf-8")

        self.assertIn("CrmCampaignAnalyticsResponse", schemas_source)
        self.assertIn("def _interaction_channel", service_source)
        self.assertIn("async def campaign_analytics", service_source)
        self.assertIn("_task_window_purchases", service_source)
        self.assertIn("_task_campaign_date", service_source)
        self.assertIn("PurchaseHistory.user_id == task.customer_id", service_source)
        self.assertIn("CustomerMessage.payload[\"generation_id\"].astext.isnot(None)", service_source)
        self.assertIn("external_sms_aero", service_source)
        self.assertIn("_message_window_purchases", service_source)
        self.assertIn('@router.get("/analytics"', admin_api)
        self.assertIn('@router.delete("/campaigns/{campaign_id}"', admin_api)
        self.assertIn("Аналитика кампаний", frontend_source)
        self.assertIn("Покупки после взаимодействия", frontend_source)

    def test_google_sheet_import_normalizes_human_labels(self):
        from scripts.import_seller_crm_tasks_from_sheet import row_to_import

        item = row_to_import({
            "__row_number": "42",
            "Телефон": "+7 978 000-00-00",
            "Дата отработки": "21.07.2026",
            "CRM группа": "B. Личное сообщение",
            "Статус работы": "Проверено / отработано",
            "Итог продавца": "Видео отправлено",
        })

        self.assertIsNotNone(item)
        self.assertEqual(item.crm_group, "personal_message")
        self.assertEqual(item.status, "worked")
        self.assertEqual(item.seller_outcome, "photo_video_sent")

        item = row_to_import({
            "__row_number": "43",
            "Телефон": "+7 978 000-00-01",
            "Дата отработки": "21.07.2026",
            "CRM группа": "0",
            "Статус работы": "Позвонили",
            "Итог продавца": "Не дозвонились",
        })

        self.assertIsNotNone(item)
        self.assertEqual(item.crm_group, "personal_message")
        self.assertEqual(item.status, "worked")
        self.assertEqual(item.seller_outcome, "no_answer")

        item = row_to_import({
            "__row_number": "46",
            "Телефон": "+7 978 000-00-04",
            "Дата отработки": "21.07.2026",
            "CRM группа": "A. Личный звонок",
            "Статус работы": "Закрыто",
            "Итог продавца": "Жалоба на качество",
        })

        self.assertIsNotNone(item)
        self.assertEqual(item.seller_outcome, "quality_complaint")

        item = row_to_import({
            "__row_number": "44",
            "Телефон": "+7 978 000-00-02",
            "Дата отработки": "21.07.2026",
            "Ответственный / чей клиент": "БЕШЛИЕВА ",
            "Магазин предпочтительный": "Меганом",
            "CRM группа": "A. Личный звонок",
        })

        self.assertIsNotNone(item)
        self.assertEqual(item.seller_name, "Бешлиева")
        self.assertEqual(item.store_name, "Мрия")

        item = row_to_import({
            "__row_number": "45",
            "Телефон": "+7 978 000-00-03",
            "Дата отработки": "21.07.2026",
            "Ответственный / чей клиент": "РОГАЛЕВИЧ ",
            "CRM группа": "A. Личный звонок",
        })

        self.assertIsNotNone(item)
        self.assertEqual(item.seller_name, "Рогалевич")

    def test_manager_kpi_scope_prefers_synced_managed_stores(self):
        from app.services.seller_kpi_service import SellerKPIService

        user = SimpleNamespace(
            role="manager",
            preferences={
                "managed_store_names": ["Мрия"],
                "staff_store": "Ялта, Набережная Ленина, 18",
                "staff_store_name": "Ялта, Набережная 18",
            },
        )

        self.assertEqual(SellerKPIService._preference_store_names(user), ["Мрия"])
        self.assertEqual(SellerKPIService._canonical_store_name("Ялта, Набережная Ленина, 18"), "Ялта, Набережная 18")


if __name__ == "__main__":
    unittest.main()
