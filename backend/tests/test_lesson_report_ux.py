import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LessonReportUxTests(unittest.TestCase):
    def test_manager_and_admin_show_lesson_quiz_report(self):
        manager = (ROOT / "frontend/src/components/training/ManagerTraineeTrainingPage.tsx").read_text(encoding="utf-8")
        admin = (ROOT / "frontend/src/components/training/ConsultantTrainingAdminPage.tsx").read_text(encoding="utf-8")

        self.assertIn("Отчёты по урокам", manager)
        self.assertIn("duration_seconds", manager)
        self.assertIn("Квиз урока:", admin)
        self.assertIn("lessonDurationLabel", admin)


if __name__ == "__main__":
    unittest.main()
