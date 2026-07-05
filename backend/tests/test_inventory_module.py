import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.inventory_control_service import InventoryRow


class FakeResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class FakeSession:
    async def execute(self, *args, **kwargs):
        return FakeResult()

    async def commit(self):
        return None


async def override_db():
    yield FakeSession()


def row(name: str, **overrides):
    defaults = dict(
        product_id=None,
        external_id=name.lower(),
        article=None,
        barcode=None,
        nomenclature=name,
        color="Red",
        category="Cat",
        brand=None,
        collection=None,
        price_cents=None,
        is_core_assortment=False,
        supports_brand_concept=False,
        sold_qty=0.0,
        revenue=0.0,
        checks_count=0,
        stock_qty=0.0,
        sales_month=0.0,
        stock_cover=None,
        status="unknown",
    )
    defaults.update(overrides)
    return InventoryRow(**defaults)


class InventoryModuleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        from app.database.connection import get_db

        app.dependency_overrides[get_db] = override_db

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_order_recommendations_formula(self):
        rows = [
            row("A", external_id="p1", price_cents=10000, sold_qty=3.0, revenue=300.0, checks_count=1, stock_qty=1.0, sales_month=1.0, stock_cover=1.0, status="reorder"),
            row("B", external_id="p2", color="Blue", price_cents=10000, sold_qty=3.0, revenue=300.0, checks_count=1, stock_qty=5.0, sales_month=1.0, stock_cover=5.0, status="overstock"),
        ]

        async def fake_build(self, **kwargs):
            return rows

        async def fake_get(self, **kwargs):
            return None

        async def fake_upsert(self, **kwargs):
            return None

        with patch("app.services.inventory_control_service.InventoryControlService.build_inventory_rows", fake_build), patch(
            "app.services.inventory_snapshot_service.InventorySnapshotService.get_fresh_snapshot", fake_get
        ), patch("app.services.inventory_snapshot_service.InventorySnapshotService.upsert_snapshot", fake_upsert):
            r = self.client.get("/api/inventory/order?use_cache=false&force_refresh=true")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["rows"][0]["nomenclature"], "A")
            self.assertAlmostEqual(float(data["rows"][0]["order_qty"]), 2.0, places=6)

    def test_clearance_protects_brand(self):
        rows = [
            row("A", external_id="p1", is_core_assortment=True, sold_qty=3.0, revenue=300.0, checks_count=1, stock_qty=10.0, sales_month=1.0, stock_cover=7.0, status="slow_moving"),
            row("B", external_id="p2", color="Blue", is_core_assortment=True, stock_qty=20.0, stock_cover=13.0, status="no_sales"),
        ]

        async def fake_build(self, **kwargs):
            return rows

        async def fake_get(self, **kwargs):
            return None

        async def fake_upsert(self, **kwargs):
            return None

        with patch("app.services.inventory_control_service.InventoryControlService.build_inventory_rows", fake_build), patch(
            "app.services.inventory_snapshot_service.InventorySnapshotService.get_fresh_snapshot", fake_get
        ), patch("app.services.inventory_snapshot_service.InventorySnapshotService.upsert_snapshot", fake_upsert):
            r = self.client.get("/api/inventory/clearance?use_cache=false&force_refresh=true")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            recs = {(x["nomenclature"], x["recommendation"]) for x in data["rows"]}
            self.assertIn(("A", "BUNDLE"), recs)
            self.assertIn(("B", "RELOCATION"), recs)

    def test_pricing_protected_uses_bundle(self):
        rows = [
            row("A", external_id="p1", is_core_assortment=True, sold_qty=1.0, revenue=100.0, checks_count=1, stock_qty=20.0, sales_month=0.2, stock_cover=10.0, status="slow_moving"),
            row("B", external_id="p2", color="Blue", sold_qty=1.0, revenue=100.0, checks_count=1, stock_qty=20.0, sales_month=0.2, stock_cover=10.0, status="slow_moving"),
        ]

        async def fake_build(self, **kwargs):
            return rows

        async def fake_get(self, **kwargs):
            return None

        async def fake_upsert(self, **kwargs):
            return None

        with patch("app.services.inventory_control_service.InventoryControlService.build_inventory_rows", fake_build), patch(
            "app.services.inventory_snapshot_service.InventorySnapshotService.get_fresh_snapshot", fake_get
        ), patch("app.services.inventory_snapshot_service.InventorySnapshotService.upsert_snapshot", fake_upsert):
            r = self.client.get("/api/inventory/pricing/report?use_cache=false&force_refresh=true")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            statuses = {x["nomenclature"]: x["pricing_status"] for x in data["rows"]}
            self.assertEqual(statuses["A"], "BUNDLE INSTEAD OF DISCOUNT")
            self.assertEqual(statuses["B"], "HEAVY DISCOUNT")

    def test_assortment_endpoint_uses_agent_sales_diagnostics_and_plan_source(self):
        async def fake_agent_build(self, **kwargs):
            return {
                "rows": [],
                "total_sales": 10.0,
                "total_stock": 20.0,
                "sales_diagnostics": {
                    "stores": [{"store_id": "yalta", "revenue": 10.0}],
                    "sellers": [{"seller_id": "seller-1", "seller_name": "Seller One", "revenue": 10.0}],
                    "brands": [],
                    "categories": [],
                    "positions": [],
                    "data_quality": {"unattributed_seller_share": 0.0, "warnings": []},
                },
                "plan_source": {
                    "source_url": "https://disk.yandex.ru/d/w9ahxGKuAN_Hag",
                    "store_name": "Ялта",
                    "store_id": "yalta",
                    "period": "2026-05",
                    "import_status": "available_for_yalta_only",
                    "warnings": ["yalta_plan_not_applicable_to_centrum"],
                },
                "warnings": None,
            }

        async def fake_get(self, **kwargs):
            return None

        async def fake_upsert(self, **kwargs):
            return None

        with patch("app.agents.inventory_assortment_matrix_agent.AssortmentMatrixAgent.build_assortment", fake_agent_build), patch(
            "app.services.inventory_snapshot_service.InventorySnapshotService.get_fresh_snapshot", fake_get
        ), patch("app.services.inventory_snapshot_service.InventorySnapshotService.upsert_snapshot", fake_upsert):
            r = self.client.get("/api/inventory/assortment?period=custom&start_date=2026-05-01&end_date=2026-05-31&store_id=centrum&seller_id=seller-1&force_refresh=true")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn("sales_diagnostics", data)
            self.assertEqual(data["sales_diagnostics"]["sellers"][0]["seller_id"], "seller-1")
            self.assertEqual(data["plan_source"]["store_name"], "Ялта")
            self.assertIn("yalta_plan_not_applicable_to_centrum", data["plan_source"]["warnings"])

    def test_assortment_warnings(self):
        rows = [
            row("A", external_id="p1", color="Red", category="Cat1", sold_qty=8.0, stock_qty=8.0, sales_month=2.0, stock_cover=4.0, status="overstock"),
            row("B", external_id="p2", color="Blue", category="Cat2", sold_qty=2.0, stock_qty=2.0, sales_month=0.5, stock_cover=4.0, status="overstock"),
        ]

        async def fake_build(self, **kwargs):
            return rows

        async def fake_get(self, **kwargs):
            return None

        async def fake_upsert(self, **kwargs):
            return None

        with patch("app.services.inventory_control_service.InventoryControlService.build_inventory_rows", fake_build), patch(
            "app.services.inventory_snapshot_service.InventorySnapshotService.get_fresh_snapshot", fake_get
        ), patch("app.services.inventory_snapshot_service.InventorySnapshotService.upsert_snapshot", fake_upsert):
            r = self.client.get("/api/inventory/assortment?use_cache=false&force_refresh=true")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn("color_share_gt_75pct", data.get("warnings") or [])
            self.assertIn("top10_sales_share_gt_60pct", data.get("warnings") or [])


class AssortmentMatrixAgentSalesDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_sales_diagnostics_blocks_personal_conclusions_without_seller_id_and_keeps_plan_source_warning(self):
        from app.agents.inventory_assortment_matrix_agent import AssortmentMatrixAgent

        agent = AssortmentMatrixAgent(FakeSession())

        async def fake_sales_rows(**kwargs):
            return [
                {
                    "store_id": "centrum",
                    "store_name": "Центрум",
                    "seller_external_id": None,
                    "seller_name": None,
                    "brand": "Brand A",
                    "category": "Кольца",
                    "sold_qty": 1.0,
                    "revenue": 100.0,
                    "checks_count": 1,
                }
            ]

        async def fake_plan_sources(**kwargs):
            return [
                {
                    "store_id": "centrum",
                    "store_name": "Центрум",
                    "period": "2026-05",
                    "source_url": "https://disk.yandex.ru/d/w9ahxGKuAN_Hag",
                    "source_file": "Yalta.xlsx",
                    "import_status": "imported",
                }
            ]

        agent._load_sales_detail_rows = fake_sales_rows
        agent._load_plan_sources = fake_plan_sources

        out = await agent.sales_effectiveness_matrix(
            start_dt=datetime(2026, 5, 1),
            end_dt=datetime(2026, 6, 1),
            store_id="centrum",
            inventory_rows=[row("Товар A", external_id="p1", article="A-1", category="Кольца", brand="Brand A", stock_qty=5.0, status="no_sales")],
        )

        self.assertEqual(
            out["diagnostics"]["seller_personal_conclusions"],
            {"blocked": True, "warning": "seller_id_missing_personal_conclusions_blocked"},
        )
        self.assertEqual(out["sellers"][0]["seller_id"], "unmatched")
        self.assertIn("unattributed_seller_share", out["data_quality"])
        self.assertIn("unmatched_seller_sales_present", out["data_quality"]["warnings"])
        self.assertIn("yalta_plan_source_must_not_be_applied_to_centrum", out["warnings"])


if __name__ == "__main__":
    unittest.main()
