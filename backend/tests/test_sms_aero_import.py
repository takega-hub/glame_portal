import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class SmsAeroImportTests(unittest.TestCase):
    def test_parser_reads_sms_aero_csv_and_maps_delivery_statuses(self):
        from app.services.sms_aero_import_service import parse_sms_aero_import_file

        csv_data = (
            "ID;Телефон;Текст;Статус;Расширенный статус;Дата отправки\n"
            "801;8 (978) 123-45-67;В GLAME 3=2 на все украшения;Доставлено;delivery;28.07.2026 10:43\n"
            "802;+7 978 765-43-21;В GLAME 3=2 на все украшения;Не доставлено;undelivered;28.07.2026 10:43\n"
        ).encode("utf-8")

        rows = parse_sms_aero_import_file("sms-aero.csv", csv_data)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].phone_normalized, "79781234567")
        self.assertEqual(rows[0].provider_id, "801")
        self.assertEqual(rows[0].status, "delivered")
        self.assertEqual(rows[0].status_code, 1)
        self.assertEqual(rows[0].status_label, "Доставлено")
        self.assertEqual(rows[1].phone_normalized, "79787654321")
        self.assertEqual(rows[1].status, "failed")
        self.assertEqual(rows[1].status_code, 2)

    def test_parser_skips_empty_rows_but_keeps_unmatched_phone_rows_for_reporting(self):
        from app.services.sms_aero_import_service import parse_sms_aero_import_file

        csv_data = (
            "number;text;status\n"
            ";Без телефона;delivery\n"
            "79780000000;Код входа GLAME: 1234;delivery\n"
            "79781111111;В GLAME 3=2;delivery\n"
        ).encode("utf-8")

        rows = parse_sms_aero_import_file("sms-aero.csv", csv_data)

        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].is_technical)
        self.assertFalse(rows[1].is_technical)

    def test_parser_reads_delivery_datetime_embedded_in_status(self):
        from app.services.sms_aero_import_service import parse_sms_aero_import_file

        csv_data = (
            "Номер;Текст;Статус\n"
            "79781234567;В GLAME 3=2;Доставлено (28.07.2026 в 10:46)\n"
        ).encode("utf-8")

        row = parse_sms_aero_import_file("sms-aero.csv", csv_data)[0]

        self.assertEqual(row.status, "delivered")
        self.assertEqual(row.sent_at.isoformat(), "2026-07-28T10:46:00+00:00")

    def test_backend_and_frontend_contract_for_sms_aero_import_exists(self):
        api_source = (ROOT / "backend/app/api/communication.py").read_text(encoding="utf-8")
        frontend_api_source = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        ui_source = (ROOT / "frontend/src/components/customers/GenerationHistoryPanel.tsx").read_text(encoding="utf-8")

        self.assertIn('/sms-aero/import', api_source)
        self.assertIn('importSmsAeroBroadcast', frontend_api_source)
        self.assertIn('Импорт рассылки SMS Aero', ui_source)


if __name__ == "__main__":
    unittest.main()
