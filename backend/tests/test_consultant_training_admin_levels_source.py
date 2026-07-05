import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "app" / "api" / "consultant_training.py"
ADMIN_PAGE = ROOT / "frontend" / "src" / "components" / "training" / "ConsultantTrainingAdminPage.tsx"


class ConsultantTrainingAdminLevelsSourceTests(unittest.TestCase):
    def test_admin_career_levels_endpoint_is_registered_and_uses_kpi(self):
        source = API.read_text(encoding="utf-8")

        self.assertIn('@router.get("/admin/consultant-training/career-levels")', source)
        self.assertIn("build_team_career_levels_payload", source)
        self.assertIn("SellerKPIService", source)
        self.assertIn('"career_levels"', source)

    def test_admin_page_loads_and_shows_career_levels_policy(self):
        source = ADMIN_PAGE.read_text(encoding="utf-8")

        self.assertIn("TrainingCareerLevels", source)
        self.assertIn("setCareerLevels", source)
        self.assertIn("/api/admin/consultant-training/career-levels", source)
        self.assertIn("Карьерные уровни и зарплатная политика", source)
        self.assertIn("Требует утверждения руководством", source)
        self.assertIn("manager_next_action", source)
        self.assertIn("level_distribution", source)


if __name__ == "__main__":
    unittest.main()
