from types import ModuleType, SimpleNamespace
import asyncio
from datetime import datetime
import sys

import pytest

# Keep this focused unit test independent from LLM/provider/database dependencies.
sqlalchemy_stub = ModuleType("sqlalchemy")

class _DummySelect:
    def where(self, *args, **kwargs):
        return self


def _select(*args, **kwargs):
    return _DummySelect()


def _and_(*args):
    return ("AND", args)


def _text(value):
    return value

sqlalchemy_stub.and_ = _and_
sqlalchemy_stub.select = _select
sqlalchemy_stub.text = _text
sys.modules.setdefault("sqlalchemy", sqlalchemy_stub)

sqlalchemy_ext_stub = ModuleType("sqlalchemy.ext")
sqlalchemy_ext_asyncio_stub = ModuleType("sqlalchemy.ext.asyncio")
sqlalchemy_ext_asyncio_stub.AsyncSession = object
sys.modules.setdefault("sqlalchemy.ext", sqlalchemy_ext_stub)
sys.modules.setdefault("sqlalchemy.ext.asyncio", sqlalchemy_ext_asyncio_stub)

base_agent_stub = ModuleType("app.agents.base_agent")
base_agent_stub.BaseAgent = object
sys.modules.setdefault("app.agents.base_agent", base_agent_stub)

class _DummyColumn:
    def __ge__(self, other):
        return True

    def __lt__(self, other):
        return True

    def __eq__(self, other):
        return True

    def in_(self, other):
        return True

models_pkg_stub = ModuleType("app.models")
models_pkg_stub.__path__ = []
sys.modules.setdefault("app.models", models_pkg_stub)

target_category_stub = ModuleType("app.models.inventory_target_category")
target_category_stub.InventoryTargetCategory = type(
    "InventoryTargetCategory",
    (),
    {"category": _DummyColumn(), "target_share": _DummyColumn(), "is_active": _DummyColumn()},
)
sys.modules.setdefault("app.models.inventory_target_category", target_category_stub)

sales_record_stub = ModuleType("app.models.sales_record")
sales_record_stub.SalesRecord = type(
    "SalesRecord",
    (),
    {
        name: _DummyColumn()
        for name in [
            "sale_date",
            "store_id",
            "product_brand",
            "product_category",
            "product_id",
            "product_name",
            "product_article",
            "quantity",
            "revenue",
            "document_id",
            "external_id",
            "raw_data",
        ]
    },
)
sys.modules.setdefault("app.models.sales_record", sales_record_stub)

store_stub = ModuleType("app.models.store")
store_stub.Store = type("Store", (), {"external_id": _DummyColumn(), "name": _DummyColumn()})
sys.modules.setdefault("app.models.store", store_stub)

inventory_service_stub = ModuleType("app.services.inventory_control_service")

class _InventoryControlServiceStub:
    def __init__(self, db=None):
        self.db = db

inventory_service_stub.InventoryControlService = _InventoryControlServiceStub
sys.modules.setdefault("app.services.inventory_control_service", inventory_service_stub)

from app.agents.inventory_assortment_matrix_agent import AssortmentMatrixAgent


class DummyAgent(AssortmentMatrixAgent):
    def __init__(self):
        self.db = None
        self.inventory = None


class DummyInventory:
    async def _resolve_store_id(self, store_id):
        return store_id

    async def build_inventory_rows(self, **kwargs):
        return []


class AsyncDummyAgent(DummyAgent):
    def __init__(self):
        self.db = None
        self.inventory = DummyInventory()

    async def _load_sales_detail_rows(self, **kwargs):
        return [
            {
                "store_id": "store-1",
                "store_name": "Центрум",
                "seller_external_id": "seller-1",
                "seller_name": kwargs.get("seller_name") or "Анна",
                "brand": "Brand",
                "category": "Кольца",
                "sold_qty": 1,
                "revenue": 1000,
                "checks_count": 1,
            }
        ]

    async def _load_plan_sources(self, **kwargs):
        return []


def inventory_row(**overrides):
    base = {
        "external_id": "product-1",
        "article": "A1",
        "barcode": "B1",
        "nomenclature": "Кольцо",
        "brand": "Brand",
        "category": "Кольца",
        "color": "Gold",
        "sold_qty": 0,
        "revenue": 0,
        "stock_qty": 3,
        "checks_count": 0,
        "stock_cover": None,
        "status": "no_sales",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_unmatched_seller_sales_are_reported_as_data_quality_warning():
    agent = DummyAgent()

    quality = agent._build_sales_data_quality(
        sales_rows=[
            {"seller_external_id": "00000000-0000-0000-0000-000000000000", "seller_name": None, "revenue": 300.0, "sold_qty": 3},
            {"seller_external_id": "seller-1", "seller_name": "Анна", "revenue": 700.0, "sold_qty": 7},
        ],
        plan_sources=[],
    )

    assert quality["unmatched_revenue_share"] == pytest.approx(0.3)
    assert "unmatched_seller_sales_present" in quality["warnings"]
    assert "unmatched_seller_share_gte_10pct" in quality["warnings"]


def test_personal_seller_conclusions_are_blocked_without_seller_scope():
    agent = DummyAgent()

    diagnostics = agent._build_sales_diagnostics(
        sales_rows=[{"seller_external_id": "seller-1", "seller_name": "Анна", "category": "Кольца", "sold_qty": 1}],
        inventory_blocks={"positions": []},
        seller_scope_warning="seller_id_missing_personal_conclusions_blocked",
    )

    assert diagnostics["seller_personal_conclusions"] == {
        "blocked": True,
        "warning": "seller_id_missing_personal_conclusions_blocked",
    }


def test_seller_name_filter_does_not_unblock_personal_conclusions_without_seller_id():
    agent = AsyncDummyAgent()

    result = asyncio.run(
        agent.sales_effectiveness_matrix(
            seller_name="Анна",
            inventory_rows=[inventory_row()],
        )
    )

    assert "seller_id_missing_personal_conclusions_blocked" in result["warnings"]
    assert result["filters"]["seller_name"] == "Анна"
    assert result["diagnostics"]["seller_personal_conclusions"] == {
        "blocked": True,
        "warning": "seller_id_missing_personal_conclusions_blocked",
    }


def test_inventory_sales_blocks_respect_positions_limit():
    agent = DummyAgent()
    rows = [inventory_row(external_id=f"p-{i}", stock_qty=i + 1) for i in range(5)]

    positions = agent._build_position_rows([], rows, limit=2)

    assert len(positions) == 2


def test_position_rows_do_not_double_count_inventory_and_sales_rows():
    agent = DummyAgent()
    rows = [inventory_row(external_id="product-1", sold_qty=2, revenue=200, stock_qty=3)]

    positions = agent._build_position_rows(
        [{"product_id": "product-1", "sold_qty": 5, "revenue": 500, "brand": "Brand", "category": "Кольца"}],
        rows,
        limit=5,
        use_detailed_sales=True,
    )

    assert positions[0]["sold_qty"] == pytest.approx(5)
    assert positions[0]["revenue"] == pytest.approx(500)
    assert positions[0]["inventory_sold_qty"] == pytest.approx(2)
    assert positions[0]["inventory_revenue"] == pytest.approx(200)
    assert positions[0]["diagnosis"] == "balanced_or_unknown"


def test_position_rows_authoritative_empty_sales_do_not_fall_back_to_inventory_sales():
    agent = DummyAgent()
    rows = [inventory_row(external_id="product-1", sold_qty=2, revenue=200, stock_qty=3)]

    positions = agent._build_position_rows([], rows, limit=5, use_detailed_sales=True)

    assert positions[0]["sold_qty"] == pytest.approx(0)
    assert positions[0]["revenue"] == pytest.approx(0)
    assert positions[0]["inventory_sold_qty"] == pytest.approx(2)
    assert positions[0]["inventory_revenue"] == pytest.approx(200)
    assert positions[0]["diagnosis"] == "stock_without_sales"


def test_seller_diagnostic_rows_block_personal_output_for_unmatched_bucket():
    agent = DummyAgent()

    rows = agent._annotate_seller_rows(
        [
            {"seller_id": "unmatched", "seller_external_id": "unmatched", "seller_name": "Не сопоставлено с продавцом"},
            {"seller_id": "seller-1", "seller_external_id": "seller-1", "seller_name": "Анна"},
        ]
    )

    assert rows[0]["personal_output_blocked"] is True
    assert rows[0]["warning"] == "seller_not_attributed_personal_output_blocked"
    assert rows[1]["personal_output_blocked"] is False


def test_yalta_plan_source_is_not_allowed_for_centrum():
    agent = DummyAgent()

    warning = agent._plan_source_warning(
        {
            "store_name": "Центрум",
            "source_url": "https://disk.yandex.ru/d/w9ahxGKuAN_Hag",
            "raw_data": {"source_file": "Yalta.xlsx"},
        }
    )

    assert warning == "yalta_plan_source_must_not_be_applied_to_centrum"


def test_platform_db_plan_source_is_primary_and_yandex_is_only_provenance():
    agent = DummyAgent()

    normalized = agent._normalize_plan_sources(
        [
            {
                "seller_external_id": "seller-1",
                "seller_name": "Анна",
                "store_id": "yalta-store",
                "store_name": "Ялта",
                "month": "2026-05-01",
                "source": "yandex_disk_import",
                "raw_data": {"source_url": "https://disk.yandex.ru/d/w9ahxGKuAN_Hag", "file_name": "may-yaltа.xlsx"},
            }
        ]
    )

    assert normalized[0]["storage"] == "platform_db"
    assert normalized[0]["import_source"] == "yandex_disk_import"
    assert normalized[0]["import_status"] == "confirmed_in_platform_db"

    plan_source = agent._build_plan_source(
        start_dt=datetime(2026, 5, 1),
        store_id="yalta-store",
        plan_sources=normalized,
    )

    assert plan_source["source_system"] == "platform_db"
    assert plan_source["storage"] == "seller_monthly_plans"
    assert plan_source["import_source"] == "yandex_disk_import"
    assert plan_source["source_url"] == "https://disk.yandex.ru/d/w9ahxGKuAN_Hag"
    assert plan_source["warnings"] == []


def test_build_category_matrix_keeps_assortment_basics():
    agent = DummyAgent()

    rows = [
        SimpleNamespace(category="Кольца", sold_qty=10, stock_qty=30),
        SimpleNamespace(category="Серьги", sold_qty=5, stock_qty=10),
    ]

    matrix, total_sales, total_stock = agent._build_category_matrix(rows, {"Кольца": 0.4, "Серьги": 0.6})

    assert total_sales == pytest.approx(15)
    assert total_stock == pytest.approx(40)
    assert {row["category"] for row in matrix} == {"Кольца", "Серьги"}
    rings = next(row for row in matrix if row["category"] == "Кольца")
    assert rings["category_share_sales"] == pytest.approx(10 / 15)
    assert rings["category_share_stock"] == pytest.approx(30 / 40)
    assert rings["warnings"] == ["target_deviation_gt_10pct"]
