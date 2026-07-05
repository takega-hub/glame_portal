import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


class SellerKpiAssortmentGuidanceTests(unittest.TestCase):
    def test_backend_has_separate_assortment_guidance_table_and_api_methods(self):
        service = (BACKEND / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")
        api = (BACKEND / "app/api/admin/onec_customers.py").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS seller_kpi_assortment_guidance", service)
        self.assertIn("assortment_block", service)
        self.assertIn("soft_guidance BOOLEAN NOT NULL DEFAULT TRUE", service)
        self.assertIn("async def assortment_guidance", service)
        self.assertIn("async def save_assortment_guidance", service)
        self.assertIn('@router.get("/sellers/kpi/assortment-guidance")', api)
        self.assertIn('@router.put("/sellers/kpi/assortment-guidance")', api)

    def test_backend_persists_yalta_june_2026_seed_rows_and_personal_proportional_guidance(self):
        service = (BACKEND / "app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        for block in ["IS", "Antura", "Raganella", "SALE", "UNOde50/Men", "Kalliope", "Claudio Canzian", "Остальное"]:
            self.assertIn(block, service)
        self.assertIn("2849458", service)
        self.assertIn("personal_sales_guidance", service)
        self.assertIn("seller_personal_plan", service)
        self.assertIn("personal_plan * share", service)
        self.assertIn("sum_sales_guidance", service)

    def test_frontend_types_and_api_client_expose_assortment_guidance(self):
        api = (FRONTEND / "src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn("SellerKpiAssortmentGuidanceRow", api)
        self.assertIn("SellerKpiAssortmentGuidanceResponse", api)
        self.assertIn("getSellerKpiAssortmentGuidance", api)
        self.assertIn("saveSellerKpiAssortmentGuidance", api)
        self.assertIn("/api/admin/1c/sellers/kpi/assortment-guidance", api)

    def test_seller_ui_renders_soft_guidance_explanation_and_skew_diagnostics(self):
        page = (FRONTEND / "src/components/profile/ProfileSellersPage.tsx").read_text(encoding="utf-8")

        self.assertIn("assortmentGuidance", page)
        self.assertIn("Ассортиментный ориентир", page)
        self.assertIn("не жёсткая квота", page)
        self.assertIn("продавать весь ассортимент", page)
        self.assertIn("personal_sales_guidance", page)
        self.assertIn("Диагностика перекосов", page)
        self.assertIn("не продавать бренды под ноль", page)
        self.assertIn("saveSellerKpiAssortmentGuidance", page)
        self.assertIn("Сохранить ассортиментный ориентир", page)
        self.assertIn("current_stock", page)
        self.assertIn("incoming", page)
        self.assertIn("stock_after_guidance", page)


if __name__ == "__main__":
    unittest.main()
