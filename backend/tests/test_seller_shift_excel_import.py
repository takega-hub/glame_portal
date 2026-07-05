import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_XLSX = Path('/root/hermes-web-ui/upload/default/7202e44c0ce176d8.xlsx')


class SellerShiftExcelImportTests(unittest.TestCase):
    def test_parser_reads_graph_sheet_numeric_marks_only(self):
        from app.services.seller_shift_excel_import_service import SellerShiftExcelParser

        self.assertTrue(SAMPLE_XLSX.exists(), 'sample schedule Excel file must be available for parser regression')
        parsed = SellerShiftExcelParser().parse_file(SAMPLE_XLSX, store_name='ТРК Центрум', source_filename='ЕО Центрум 05.2026.xlsx')

        self.assertEqual(parsed['period_month'], '2026-05')
        self.assertEqual(parsed['store_name'], 'ТРК Центрум')
        self.assertEqual(parsed['source_sheet'], 'График')
        self.assertGreaterEqual(len(parsed['shifts']), 35)

        beshlieva_dates = {row['shift_date'] for row in parsed['shifts'] if row['seller_name'] == 'Бешлиева Аджере'}
        gelmel_dates = {row['shift_date'] for row in parsed['shifts'] if row['seller_name'] == 'Гельмель Юлия'}

        self.assertIn('2026-05-01', beshlieva_dates)
        self.assertIn('2026-05-08', beshlieva_dates)  # 7.5 is a worked shift
        self.assertIn('2026-05-27', beshlieva_dates)  # 2 is a worked shift
        self.assertNotIn('2026-05-12', beshlieva_dates)  # в = absence, not a shift
        self.assertNotIn('2026-05-04', gelmel_dates)  # 6с has suffix and is excluded
        self.assertNotIn('2026-05-05', gelmel_dates)  # 11с has suffix and is excluded
        self.assertIn('2026-05-13', gelmel_dates)  # pure 11 is included

        sample = next(row for row in parsed['shifts'] if row['seller_name'] == 'Бешлиева Аджере' and row['shift_date'] == '2026-05-01')
        self.assertEqual(sample['starts_at'], '10:00')
        self.assertEqual(sample['ends_at'], '21:00')
        self.assertIn('Импорт из Excel май 2026: 11; должность АМ', sample['note'])

    def test_backend_api_exposes_shift_excel_import_endpoint(self):
        source = (ROOT / 'backend/app/api/admin/onec_customers.py').read_text(encoding='utf-8')
        self.assertIn('@router.post("/sellers/shifts/import-excel")', source)
        self.assertIn('UploadFile', source)
        self.assertIn('import_seller_shifts_from_excel_upload', source)

    def test_frontend_has_schedule_excel_upload_flow(self):
        page = (ROOT / 'frontend/src/components/profile/ProfileSellersPage.tsx').read_text(encoding='utf-8')
        api = (ROOT / 'frontend/src/lib/api.ts').read_text(encoding='utf-8')
        self.assertIn('importSellerShiftsExcel', api)
        self.assertIn('/api/admin/1c/sellers/shifts/import-excel', api)
        self.assertIn('Загрузить график из Excel', page)
        self.assertIn('Предпросмотр', page)
        self.assertIn('Применить импорт', page)


if __name__ == '__main__':
    unittest.main()
