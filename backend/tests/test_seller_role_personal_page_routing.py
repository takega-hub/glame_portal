import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SellerRolePersonalPageRoutingTests(unittest.TestCase):
    def test_sidebar_routes_seller_role_to_personal_kpi_not_main_dashboard(self):
        navigation_source = (ROOT / "frontend/src/config/navigation.ts").read_text(encoding="utf-8")
        sidebar_source = (ROOT / "frontend/src/components/layout/GlobalSidebar.tsx").read_text(encoding="utf-8")

        self.assertIn("sellerHref", navigation_source)
        self.assertIn("/profile/sellers/personal", navigation_source)
        self.assertIn("resolveNavHref(item, user?.role)", sidebar_source)
        self.assertNotIn("href={item.href}", sidebar_source)

    def test_dashboard_route_redirects_seller_role_to_personal_page(self):
        dashboard_page = (ROOT / "frontend/src/app/profile/sellers/dashboard/page.tsx").read_text(encoding="utf-8")

        self.assertIn("useAuth", dashboard_page)
        self.assertIn("router.replace('/profile/sellers/personal')", dashboard_page)
        self.assertIn("if (user?.role === 'seller')", dashboard_page)

    def test_personal_kpi_page_supports_current_seller_without_query_params(self):
        personal_source = (ROOT / "frontend/src/components/profile/SellerPersonalKpiPage.tsx").read_text(encoding="utf-8")

        self.assertIn("useAuth", personal_source)
        self.assertIn("isSelfSellerPage", personal_source)
        self.assertIn("canUseSelfFallback", personal_source)
        self.assertIn("rows[0] || null", personal_source)
        self.assertNotIn("Главный дашборд</Link>", personal_source)

    def test_personal_kpi_page_uses_selected_preview_account_before_self_fallback(self):
        personal_source = (ROOT / "frontend/src/components/profile/SellerPersonalKpiPage.tsx").read_text(encoding="utf-8")

        self.assertIn("accountPreview", personal_source)
        self.assertIn("previewNeedsAccount", personal_source)
        self.assertIn("accountPreview?.full_name", personal_source)
        self.assertIn("user?.is_role_preview", personal_source)
        self.assertIn("Выберите конкретный аккаунт продавца", personal_source)

    def test_backend_self_scope_matches_full_or_short_seller_names_not_only_exact_equal(self):
        service_source = (ROOT / "backend/app/services/seller_kpi_service.py").read_text(encoding="utf-8")

        self.assertIn("def _seller_identity_candidates", service_source)
        self.assertIn("def _matches_seller_identity", service_source)
        self.assertNotIn("row.get(\"seller_name\") or \"\").strip().lower() == user_name.lower()", service_source)


if __name__ == "__main__":
    unittest.main()
