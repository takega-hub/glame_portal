import unittest

from app.services.trainee_attestation import TRAINEE_FINAL_QUESTIONS, trainee_attestation_task, trainee_evaluation_fallback


class TraineeAttestationTests(unittest.TestCase):
    def test_task_is_learner_safe_and_covers_the_supplied_blank(self):
        task = trainee_attestation_task()

        self.assertEqual(task["source"], "Бланк стажера 2025")
        self.assertEqual(task["time_limit_minutes"], 45)
        self.assertIn("45 минут", task["time_limit_message"])
        self.assertGreaterEqual(len(task["questions"]), 20)
        self.assertNotIn("keywords", task["questions"][0])
        self.assertEqual({item["id"] for item in task["questions"]}, {item["id"] for item in TRAINEE_FINAL_QUESTIONS})

    def test_fallback_returns_a_result_for_every_question(self):
        answers = {item["id"]: "Я объясню покупателю свойства украшения, выгоду для образа и покажу пример в ассортименте." for item in TRAINEE_FINAL_QUESTIONS}
        evaluation = trainee_evaluation_fallback(answers)

        self.assertEqual(evaluation["max_score"], 100)
        self.assertEqual(len(evaluation["question_results"]), len(TRAINEE_FINAL_QUESTIONS))
        self.assertTrue(evaluation["requires_manager_review"])


if __name__ == "__main__":
    unittest.main()
