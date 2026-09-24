import unittest

from app.services.trainee_lesson_flow import evaluate_trainee_lesson_quiz, trainee_lesson_flow


class TraineeLessonFlowTests(unittest.TestCase):
    def test_lesson_flow_is_safe_for_learner(self):
        flow = trainee_lesson_flow("Миссия и ценности GLAME", "Один принцип.", "Фокус.", "Практика.")

        self.assertEqual(len(flow["slides"]), 3)
        self.assertEqual(len(flow["quiz"]), 3)
        self.assertNotIn("answer", flow["quiz"][0])

    def test_quiz_requires_two_correct_answers(self):
        result = evaluate_trainee_lesson_quiz("Миссия и ценности GLAME", {
            "mission_focus": "Помочь подобрать украшение под образ и потребность",
            "mission_tone": "Внимательный и без давления",
            "mission_uncertain": "Не отвечать покупателю",
        })

        self.assertTrue(result["passed"])
        self.assertEqual(result["correct_answers"], 2)


if __name__ == "__main__":
    unittest.main()
