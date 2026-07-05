import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "components" / "training" / "SellerTrainingPage.tsx"


class SellerTrainingPageUXTests(unittest.TestCase):
    def test_page_promotes_assignments_as_primary_learning_flow(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("primaryProgram", source)
        self.assertIn("Главное задание", source)
        self.assertIn("Начать обучение", source)
        self.assertIn("Продолжить обучение", source)
        self.assertIn("Открыть задание", source)
        self.assertIn("Сначала урок", source)
        self.assertIn("Потом практика", source)
        self.assertIn("AI-наставник ведет", source)

    def test_page_does_not_tell_seller_mentor_chat_is_future_when_it_exists(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertNotIn("Чат с AI-наставником запланирован следующим инкрементом", source)
        self.assertIn("Напишите наставнику", source)
        self.assertIn("askMentor(primaryProgram", source)

    def test_optional_training_widgets_are_tolerant_to_not_found_backend_routes(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("dailyFocusResponse?.data?.daily_focus", source)
        self.assertIn("currentTaskResponse?.data?.current_task", source)
        self.assertIn("reflectionsResponse?.data?.reflections", source)
        self.assertIn("coachingResponse?.data?.coaching_actions", source)
        self.assertIn("catch(() => null)", source)

    def test_current_assignment_explains_task_execution_and_assessment(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Что это за задание", source)
        self.assertIn("Что нужно сделать", source)
        self.assertIn("Шаблон ответа", source)
        self.assertIn("Как будет оцениваться", source)
        self.assertIn("Что будет дальше", source)
        self.assertIn("startPrimaryLearning", source)
        self.assertIn("trainingWorkspaceRef", source)

    def test_page_explains_long_term_mentor_and_level_salary_track(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("AI-наставник ведет продавца постоянно", source)
        self.assertIn("Уровни и рост", source)
        self.assertIn("зарплат", source)
        self.assertIn("знания", source)
        self.assertIn("реальные продажи", source)

    def test_page_shows_next_level_requirements_from_career_payload(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("setCareerLevel", source)
        self.assertIn("currentTaskResponse?.data?.career_level", source)
        self.assertIn("Что нужно для следующего уровня", source)
        self.assertIn("requirements_to_next_level", source)
        self.assertIn("score_breakdown", source)
        self.assertIn("salary_policy", source)


if __name__ == "__main__":
    unittest.main()
