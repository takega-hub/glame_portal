import importlib
import sys
import types
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def install_dependency_stubs():
    sqlalchemy = types.ModuleType("sqlalchemy")

    class DummySelect:
        def where(self, *args, **kwargs):
            return self

    def select(*args, **kwargs):
        return DummySelect()

    def text(value):
        return value

    def and_(*args):
        return ("AND", args)

    sqlalchemy.and_ = and_
    sqlalchemy.select = select
    sqlalchemy.text = text
    sys.modules.setdefault("sqlalchemy", sqlalchemy)

    sqlalchemy_ext = types.ModuleType("sqlalchemy.ext")
    sqlalchemy_ext_asyncio = types.ModuleType("sqlalchemy.ext.asyncio")

    class AsyncSession:
        pass

    sqlalchemy_ext_asyncio.AsyncSession = AsyncSession
    sys.modules.setdefault("sqlalchemy.ext", sqlalchemy_ext)
    sys.modules.setdefault("sqlalchemy.ext.asyncio", sqlalchemy_ext_asyncio)

    base_agent = types.ModuleType("app.agents.base_agent")

    class BaseAgent:
        def __init__(self, *args, **kwargs):
            pass

    base_agent.BaseAgent = BaseAgent
    sys.modules["app.agents.base_agent"] = base_agent

    target_category = types.ModuleType("app.models.inventory_target_category")

    class _TargetShare:
        def __eq__(self, other):
            return True

    class InventoryTargetCategory:
        is_active = _TargetShare()

    target_category.InventoryTargetCategory = InventoryTargetCategory
    sys.modules["app.models.inventory_target_category"] = target_category

    class DummyColumn:
        def __ge__(self, other):
            return (">=", other)

        def __lt__(self, other):
            return ("<", other)

        def __eq__(self, other):
            return ("=", other)

        def in_(self, other):
            return ("IN", other)

    sales_record = types.ModuleType("app.models.sales_record")

    class SalesRecord:
        sale_date = DummyColumn()
        store_id = DummyColumn()
        product_brand = DummyColumn()
        product_category = DummyColumn()
        product_id = DummyColumn()
        product_name = DummyColumn()
        product_article = DummyColumn()
        quantity = DummyColumn()
        revenue = DummyColumn()
        document_id = DummyColumn()
        external_id = DummyColumn()
        raw_data = DummyColumn()

    sales_record.SalesRecord = SalesRecord
    sys.modules["app.models.sales_record"] = sales_record

    store = types.ModuleType("app.models.store")

    class Store:
        external_id = DummyColumn()
        name = DummyColumn()

    store.Store = Store
    sys.modules["app.models.store"] = store

    inventory_service = types.ModuleType("app.services.inventory_control_service")

    class InventoryControlService:
        def __init__(self, db):
            self.db = db

    inventory_service.InventoryControlService = InventoryControlService
    sys.modules["app.services.inventory_control_service"] = inventory_service

    seller_kpi = types.ModuleType("app.services.seller_kpi_service")
    seller_kpi.KNOWN_SELLER_NAMES_BY_EXTERNAL_ID = {"seller-1": "Анна"}
    seller_kpi.SELLER_KEY_EXPR = "seller_key_expr"
    seller_kpi.SELLER_NAME_EXPR = "seller_name_expr"
    seller_kpi.STORE_EXPR = "store_expr"
    seller_kpi.ZERO_GUID = "00000000-0000-0000-0000-000000000000"
    sys.modules["app.services.seller_kpi_service"] = seller_kpi


install_dependency_stubs()
assortment_module = importlib.import_module("app.agents.inventory_assortment_matrix_agent")
AssortmentMatrixAgent = assortment_module.AssortmentMatrixAgent
ZERO_GUID = sys.modules["app.services.seller_kpi_service"].ZERO_GUID


class AssortmentSalesDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.agent = AssortmentMatrixAgent(db=None)

    def test_unmatched_seller_sales_are_reported_as_data_quality_warning(self):
        sales_rows = self.agent._normalize_sales_detail_rows(
            [
                {"seller_external_id": "", "seller_name": None, "sold_qty": 2, "revenue": 100},
                {"seller_external_id": "seller-1", "seller_name": "Анна", "sold_qty": 3, "revenue": 900},
            ]
        )
        quality = self.agent._build_sales_data_quality(sales_rows=sales_rows, plan_sources=[])

        self.assertEqual(quality["unmatched_revenue"], 100)
        self.assertEqual(quality["unmatched_revenue_share"], 0.1)
        self.assertIn("unmatched_seller_sales_present", quality["warnings"])
        self.assertIn("unmatched_seller_share_gte_10pct", quality["warnings"])

    def test_personal_seller_conclusions_are_blocked_without_seller_id(self):
        diagnostics = self.agent._build_sales_diagnostics(
            sales_rows=[{"seller_id": "unmatched", "seller_name": "Не сопоставлено с продавцом", "category": "Кольца", "sold_qty": 1, "seller_attributed": False}],
            inventory_rows=[],
            seller_scope_warning="seller_id_missing_personal_conclusions_blocked",
        )

        self.assertTrue(diagnostics["seller_personal_conclusions"]["blocked"])
        self.assertEqual(
            diagnostics["seller_personal_conclusions"]["warning"],
            "seller_id_missing_personal_conclusions_blocked",
        )

    def test_yalta_plan_source_is_rejected_for_centrum_store(self):
        warning = self.agent._plan_source_warning(
            {
                "store_name": "Центрум",
                "source_url": "https://disk.yandex.ru/d/w9ahxGKuAN_Hag",
                "raw_data": {"source_file": "План Ялта май.xlsx"},
            }
        )

        self.assertEqual(warning, "yalta_plan_source_must_not_be_applied_to_centrum")

    def test_normalization_keeps_unmatched_seller_rows_non_attributed(self):
        rows = self.agent._normalize_sales_detail_rows(
            [
                {
                    "store_id": "yalta",
                    "store_name": "Ялта",
                    "seller_external_id": "",
                    "seller_name": None,
                    "sold_qty": 1,
                    "revenue": 500,
                    "check_id": "check-1",
                }
            ]
        )

        self.assertEqual(rows[0]["seller_id"], "unmatched")
        self.assertEqual(rows[0]["seller_name"], "Не сопоставлено с продавцом")
        self.assertFalse(rows[0]["seller_attributed"])

    def test_zero_guid_seller_rows_are_treated_as_unmatched(self):
        rows = self.agent._normalize_sales_detail_rows(
            [
                {
                    "seller_id": ZERO_GUID,
                    "seller_external_id": ZERO_GUID,
                    "seller_name": "",
                    "sold_qty": 1,
                    "revenue": 500,
                }
            ]
        )

        self.assertEqual(rows[0]["seller_id"], "unmatched")
        self.assertEqual(rows[0]["seller_external_id"], "unmatched")
        self.assertFalse(rows[0]["seller_attributed"])

    def test_extract_seller_uses_kpi_known_name_map_when_raw_name_missing(self):
        key, name, external_id = self.agent._extract_seller({"Продавец_Key": "seller-1"})

        self.assertEqual(key, "seller-1")
        self.assertEqual(external_id, "seller-1")
        self.assertEqual(name, "Анна")

    def test_seller_rows_mark_unmatched_bucket_as_blocked_personal_output(self):
        rows = self.agent._annotate_seller_rows(
            [
                {"seller_id": "unmatched", "seller_external_id": "unmatched", "seller_name": "Не сопоставлено с продавцом", "revenue": 100},
                {"seller_id": "seller-1", "seller_external_id": "seller-1", "seller_name": "Анна", "revenue": 900},
            ]
        )

        self.assertTrue(rows[0]["personal_output_blocked"])
        self.assertEqual(rows[0]["warning"], "seller_not_attributed_personal_output_blocked")
        self.assertFalse(rows[1]["personal_output_blocked"])


if __name__ == "__main__":
    unittest.main()
