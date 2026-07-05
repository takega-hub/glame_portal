import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.admin import onec_customers
from app.services.inventory_control_service import InventoryRow
from app.services.inventory_management_service import InventoryManagementService


class OneCInventoryStatusRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_onec_sync_status_does_not_bool_evaluate_sqlalchemy_column(self):
        fake_user = MagicMock()
        fake_db = AsyncMock()
        fake_total_result = MagicMock()
        fake_total_row = MagicMock()
        fake_total_row.total_customers = 6216
        fake_total_result.first.return_value = fake_total_row
        fake_last_sync_result = MagicMock()
        fake_last_sync_result.scalar.return_value = None
        fake_db.execute.side_effect = [fake_total_result, fake_last_sync_result]

        with patch.object(onec_customers.User.__table__.columns, "get", side_effect=onec_customers.User.__table__.columns.get):
            result = await onec_customers.get_sync_status(current_user=fake_user, db=fake_db)

        self.assertEqual(result["total_customers"], 6216)
        self.assertIn("last_sync", result)

    async def test_inventory_health_score_falls_back_to_live_stock_rows_when_analytics_table_empty(self):
        fake_db = AsyncMock()
        empty_result = MagicMock()
        empty_result.first.return_value = (0, None, None, None, 0, 0)
        fake_db.execute.return_value = empty_result

        rows = [
            InventoryRow(
                product_id="p1",
                external_id="ext-1",
                article="A1",
                barcode=None,
                nomenclature="Ring A",
                color="Gold",
                category="Rings",
                brand="GLAME",
                collection=None,
                price_cents=10000,
                is_core_assortment=False,
                supports_brand_concept=False,
                sold_qty=3.0,
                revenue=30000.0,
                checks_count=2,
                stock_qty=1.0,
                sales_month=3.0,
                stock_cover=0.33,
                status="critical_stock",
            ),
            InventoryRow(
                product_id="p2",
                external_id="ext-2",
                article="B1",
                barcode=None,
                nomenclature="Necklace B",
                color="Silver",
                category="Necklaces",
                brand="GLAME",
                collection=None,
                price_cents=20000,
                is_core_assortment=False,
                supports_brand_concept=False,
                sold_qty=0.0,
                revenue=0.0,
                checks_count=0,
                stock_qty=10.0,
                sales_month=0.0,
                stock_cover=None,
                status="no_sales",
            ),
        ]

        with patch("app.services.inventory_control_service.InventoryControlService.build_inventory_rows", new=AsyncMock(return_value=rows)):
            health = await InventoryManagementService(fake_db).get_health_score()

        self.assertNotEqual(health["status"], "no_data")
        self.assertEqual(health["metrics"]["total_products"], 2)
        self.assertEqual(health["metrics"]["stock_total"], 11.0)
        self.assertLessEqual(health["health_score"], 100.0)
        self.assertNotEqual(health["status"], "excellent")


if __name__ == "__main__":
    unittest.main()
