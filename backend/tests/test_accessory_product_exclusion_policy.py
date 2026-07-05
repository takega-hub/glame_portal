import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AccessoryProductExclusionPolicyTests(unittest.TestCase):
    def test_shared_policy_classifies_accessories_by_text_article_and_id(self):
        from app.services.sales_record_filters import is_accessory_product, is_analytics_eligible_product

        self.assertTrue(is_accessory_product(product_name="Подарочная упаковка GLAME"))
        self.assertTrue(is_accessory_product(product_name="Холдер для украшений GLAME"))
        self.assertTrue(is_accessory_product(product_name="Карточка по уходу UNOde50"))
        self.assertTrue(is_accessory_product(product_category="Сопутствующие материалы"))
        self.assertTrue(is_accessory_product(product_article="400123"))
        self.assertTrue(is_accessory_product(product_id="1fee8e94-bdab-11f0-9138-fa163e4cc04e"))
        self.assertFalse(is_accessory_product(product_name="Кольцо Claudio Canzian", product_article="A123"))
        self.assertTrue(is_analytics_eligible_product(product_name="Кольцо Claudio Canzian", product_article="A123"))
        self.assertFalse(is_analytics_eligible_product(product_name="Футляр подарочный"))

    def test_seller_kpi_fact_totals_exclude_accessories_from_revenue_checks_and_items(self):
        source = (ROOT / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        self.assertIn("from app.services.sales_record_filters import", source)
        self.assertIn("ANALYTICS_ELIGIBLE_PRODUCT_SQL", source)
        self.assertIn("COALESCE(SUM(CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.revenue ELSE 0 END), 0)::float AS revenue", source)
        self.assertIn("COUNT(DISTINCT CASE WHEN {ANALYTICS_ELIGIBLE_PRODUCT_SQL} THEN sr.document_id ELSE NULL END)::int AS checks", source)
        self.assertNotIn("COALESCE(SUM(sr.revenue), 0)::float AS revenue", source)
        self.assertNotIn("COUNT(DISTINCT sr.document_id)::int AS checks", source)

    def test_product_analytics_applies_shared_accessory_filter_to_all_product_groups(self):
        source = (ROOT / "app/services/product_analytics_service.py").read_text(encoding="utf-8")
        turnover_source = (ROOT / "app/services/product_turnover_service.py").read_text(encoding="utf-8")

        self.assertIn("sales_record_eligible_product_filter", source)
        self.assertGreaterEqual(source.count("sales_record_eligible_product_filter("), 4)
        self.assertNotIn("SalesRecord.revenue / SalesRecord.quantity >= 3.0", source)
        self.assertIn("sales_record_eligible_product_filter(SalesRecord, func, and_, Product)", turnover_source)

    def test_customer_purchase_history_total_uses_filtered_rows_not_hidden_accessories(self):
        source = (ROOT / "app/api/admin/customers.py").read_text(encoding="utf-8")

        self.assertIn("is_analytics_eligible_product", source)
        self.assertIn("deduped_with_accessories", source)
        self.assertIn("total_sum = sum((p.total_amount or 0) for p, _, _, _, _, _ in deduped)", source)
        self.assertNotIn("for p, _, _, _, _, _ in deduped_with_packaging", source)

    def test_customer_sync_metrics_use_shared_accessory_filter(self):
        source = (ROOT / "app/services/customer_sync_service.py").read_text(encoding="utf-8")

        self.assertIn("from app.services.sales_record_filters import is_analytics_eligible_product", source)
        self.assertIn("filtered = [\n                p for p in purchases\n                if is_analytics_eligible_product(", source)
        self.assertIn("total_purchases = len(deduped)", source)
        self.assertNotIn("filtered = [p for p in purchases if (p.total_amount or 0) >= PACKAGING_THRESHOLD]", source)

    def test_ai_assortment_board_uses_jewelry_only_policy(self):
        inventory_source = (ROOT / "app/services/inventory_control_service.py").read_text(encoding="utf-8")
        agent_source = (ROOT / "app/agents/inventory_assortment_matrix_agent.py").read_text(encoding="utf-8")
        api_source = (ROOT / "app/api/inventory.py").read_text(encoding="utf-8")

        self.assertIn("is_analytics_eligible_product", inventory_source)
        self.assertIn("sales_record_eligible_product_filter(SalesRecord, func, and_)", inventory_source)
        self.assertIn("continue  # accessory/supplementary item", inventory_source)
        self.assertIn("sales_record_eligible_product_filter(SalesRecord, func, and_)", agent_source)
        self.assertIn("product_eligible_filter(Product, func, and_)", api_source)
        self.assertIn("sales_record_eligible_product_filter(SalesRecord, func, and_)", api_source)

    def test_ai_assortment_hides_zero_stores_and_labels_warehouse_as_online_sales(self):
        inventory_source = (ROOT / "app/services/inventory_control_service.py").read_text(encoding="utf-8")
        agent_source = (ROOT / "app/agents/inventory_assortment_matrix_agent.py").read_text(encoding="utf-8")

        self.assertIn('ONLINE_SALES_STORE_LABEL = "Сайт и приложение"', agent_source)
        self.assertIn('"e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e"', agent_source)
        self.assertIn("_normalize_store_name", agent_source)
        self.assertIn("_has_meaningful_metrics", agent_source)
        self.assertIn("if not AssortmentMatrixAgent._has_meaningful_metrics(item):", agent_source)
        self.assertIn("continue", agent_source)
        self.assertIn("if stock_qty <= 0 and sold_qty <= 0 and revenue <= 0:", inventory_source)


if __name__ == "__main__":
    unittest.main()
