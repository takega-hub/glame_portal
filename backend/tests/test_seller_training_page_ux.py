import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "components" / "training" / "LearnerTrainingPage.tsx"


class SellerTrainingPageUXTests(unittest.TestCase):
    def test_page_promotes_one_next_action_as_primary_learning_flow(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Ваша программа", source)
        self.assertIn("Открыть урок", source)
        self.assertIn("Структура программы", source)
        self.assertNotIn("Практика к смене", source)
        self.assertIn("Суть урока", source)
        self.assertIn("Держите фокус", source)
        self.assertIn("Сделайте в смене", source)
        self.assertIn("Результат задания", source)
        self.assertNotIn("Другие маршруты", source)
        self.assertNotIn("Программы обучения", source)
        self.assertIn('role="dialog"', source)
        self.assertIn("Открыть урок", source)
        self.assertIn("Перейти к опроснику", source)
        self.assertIn("Завершить урок", source)
        self.assertIn("/quiz-start", source)

    def test_page_keeps_mentor_as_a_secondary_help_action(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Спросите AI-наставника", source)
        self.assertIn("/api/profile/training/mentor/ask", source)
        self.assertIn("Финальное решение по ответу остаётся за руководителем", source)

    def test_page_loads_the_final_trainee_check_when_available(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("/api/profile/training/programs", source)
        self.assertNotIn("/api/profile/training/topics", source)
        self.assertIn("/api/profile/training/current-task", source)
        self.assertIn("Promise.all", source)
        self.assertIn("openProgram(selectedProgram, false)", source)
        self.assertIn("/api/profile/training/attestations", source)
        self.assertIn("Итоговая проверка стажёра", source)
        self.assertIn("Пройти итоговую проверку", source)


if __name__ == "__main__":
    unittest.main()
