import unittest
from pathlib import Path


class SellerKPIReceiptFactsTests(unittest.TestCase):
    def test_target_indicators_use_direct_receipt_fact_totals_for_selected_store(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        self.assertIn("async def _sales_fact_totals", source)
        self.assertIn("sales_facts = await self._sales_fact_totals", source)
        self.assertIn('facts = {\n            "revenue": sales_facts["revenue"]', source)

    def test_sales_fact_totals_use_shared_accessory_exclusion_policy(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        self.assertIn("ANALYTICS_ELIGIBLE_PRODUCT_SQL", source)
        self.assertIn("COALESCE(SUM(CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END), 0)::float AS revenue", source)
        self.assertIn("COUNT(DISTINCT CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.document_id ELSE NULL END)::int AS checks", source)
        self.assertIn("FROM sales_records sr", source)
        self.assertIn("LOWER(COALESCE(s.name, sr.store_id)) = LOWER(:store_name)", source)

    def test_dashboard_uses_direct_store_sales_facts_not_seller_row_sum(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        self.assertIn("store_facts = await self._sales_fact_totals", source)
        self.assertIn("revenue = float(store_facts[\"revenue\"] or 0)", source)
        self.assertNotIn("revenue = sum(float(row.get(\"revenue\") or 0) for row in store_sellers)", source)


if __name__ == "__main__":
    unittest.main()
