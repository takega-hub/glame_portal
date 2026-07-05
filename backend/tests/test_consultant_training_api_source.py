import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "app" / "api" / "consultant_training.py"
MAIN = ROOT / "backend" / "app" / "main.py"


class ConsultantTrainingAPISourceTests(unittest.TestCase):
    def test_profile_training_current_task_endpoint_is_registered(self):
        source = API.read_text(encoding="utf-8")

        self.assertIn('@router.get("/profile/training/current-task")', source)
        self.assertIn("build_current_learning_task_payload", source)
        self.assertIn("daily_focus", source)
        self.assertIn("competency_profile", source)

    def test_consultant_training_router_is_included_under_api_prefix(self):
        source = MAIN.read_text(encoding="utf-8")

        self.assertIn("consultant_training", source)
        self.assertIn('app.include_router(consultant_training.router, prefix="/api"', source)


if __name__ == "__main__":
    unittest.main()
