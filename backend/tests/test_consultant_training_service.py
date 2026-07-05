import base64
import io
import unittest
import zipfile

from app.services.consultant_training_service import (
    DEFAULT_TRAINING_PROGRAMS,
    apply_step_submission_progress,
    build_attestation_payload,
    build_competency_profile_payload,
    build_mentor_message_payload,
    build_mentor_reply,
    build_mentor_reply_with_library_context,
    build_management_analytics_payload,
    build_training_kpi_linkage_payload,
    build_personal_training_kpi_summary_payload,
    build_seller_training_account_matching_payload,
    build_seller_training_account_preferences_update,
    build_seller_daily_training_focus_payload,
    build_current_learning_task_payload,
    build_training_mentor_session_payload,
    build_training_material_practice_assignment_payload,
    build_seller_career_level_payload,
    build_team_career_levels_payload,
    build_schedule_aware_training_focus_payload,
    build_shift_reflection_payload,
    build_coaching_action_payload,
    build_training_material_library_payload,
    build_training_material_payload,
    build_training_material_source_file_payload,
    build_training_material_visual_assets_payload,
    extract_training_pdf_visual_assets,
    build_training_material_visual_asset_update_payload,
    build_training_material_search_payload,
    build_training_material_context_payload,
    build_training_material_detail_payload,
    build_training_material_status_change_payload,
    build_training_material_publish_cascade_payload,
    build_training_material_slide_payload,
    build_training_material_slides_payload,
    build_training_material_slide_progress_payload,
    build_training_material_slides_progress_payload,
    build_training_material_progress_analytics_payload,
    build_training_material_learning_pack_payload,
    build_step_material_practice_gate_payload,
    build_step_material_link_payload,
    build_unlocked_step_materials_payload,
    parse_training_material_markdown_import,
    parse_training_material_document_import,
    build_training_document_extraction_diagnostics,
    build_training_material_extraction_review_payload,
    build_training_material_publish_gate_payload,
    build_document_extractor_status_payload,
    build_training_material_retry_extraction_payload,
    build_training_material_bulk_import_payload,
    enrich_training_material_import_metadata,
    normalize_coaching_action_status,
    normalize_training_material_status,
    build_program_card_payload,
    build_program_assignment_removal_payload,
    normalize_attestation_status,
    build_program_structure_payload,
    build_step_submission_payload,
    evaluate_submission_quality,
    normalize_mentor_message_role,
    normalize_program_status,
    normalize_step_submission_status,
    normalize_topic_status,
    should_request_revision,
)


class ConsultantTrainingServiceTests(unittest.TestCase):
    def test_low_quality_submission_requests_delicate_revision(self):
        result = evaluate_submission_quality(
            "Красивые модные серьги, всем подходят, берите.",
            expected_focus="объяснить украшение через эффект на образ",
        )

        self.assertLessEqual(result["score"], 4)
        self.assertEqual(result["recommendation"], "request_revision")
        self.assertTrue(should_request_revision(result))
        self.assertIn("доработ", result["review_comment"].lower())
        self.assertNotIn("плохо", result["review_comment"].lower())
        self.assertNotIn("как попало", result["review_comment"].lower())

    def test_glame_language_submission_is_accepted_for_review(self):
        result = evaluate_submission_quality(
            "Эти серьги добавляют образу характер, но не перегружают. "
            "Их легко представить с белой рубашкой или спокойным платьем, "
            "когда образу нужен один понятный акцент. Следующим шагом можно добавить кольцо в такой же мягкой форме.",
            expected_focus="объяснить украшение через эффект на образ",
        )

        self.assertGreaterEqual(result["score"], 8)
        self.assertEqual(result["recommendation"], "accept")
        self.assertFalse(should_request_revision(result))
        self.assertEqual(result["status"], "feedback_review")

    def test_topic_status_requires_approval_before_publish(self):
        self.assertEqual(normalize_topic_status("approved"), "approved")
        self.assertEqual(normalize_topic_status("sent_to_consultants"), "sent_to_consultants")
        self.assertEqual(normalize_topic_status("unknown"), "draft")

    def test_default_programs_include_trainee_and_stylist_tracks(self):
        codes = [program["code"] for program in DEFAULT_TRAINING_PROGRAMS]

        self.assertEqual(codes, ["trainee_base", "stylist_academy"])
        self.assertEqual(DEFAULT_TRAINING_PROGRAMS[0]["title"], "Программа стажера GLAME")
        self.assertEqual(DEFAULT_TRAINING_PROGRAMS[1]["title"], "Программа стилиста GLAME")
        self.assertTrue(DEFAULT_TRAINING_PROGRAMS[0]["is_required"])
        self.assertTrue(DEFAULT_TRAINING_PROGRAMS[1]["is_required"])

    def test_program_status_normalization_keeps_safe_default(self):
        self.assertEqual(normalize_program_status("in_progress"), "in_progress")
        self.assertEqual(normalize_program_status("certified"), "certified")
        self.assertEqual(normalize_program_status("unexpected"), "available")
        self.assertEqual(normalize_program_status(None), "available")

    def test_program_assignment_removal_archives_without_deleting_history(self):
        enrollment = {
            "id": "enrollment-1",
            "status": "in_progress",
            "meta": {"step_progress": {"step-1": {"status": "accepted"}}, "assignment_note": "пилот"},
        }

        payload = build_program_assignment_removal_payload(
            enrollment=enrollment,
            removed_by_user_id="manager-1",
            note="Оставляем только программу стилиста",
        )

        self.assertEqual(payload["status"], "archived")
        self.assertEqual(payload["previous_status"], "in_progress")
        self.assertEqual(payload["meta"]["step_progress"], {"step-1": {"status": "accepted"}})
        self.assertEqual(payload["meta"]["unassigned_by_user_id"], "manager-1")
        self.assertEqual(payload["meta"]["unassignment_note"], "Оставляем только программу стилиста")
        self.assertTrue(payload["meta"]["unassigned_at"])

    def test_program_card_payload_blocks_archived_unassigned_course(self):
        payload = build_program_card_payload(
            program={"id": "p1", "code": "trainee_base", "title": "Программа стажера GLAME"},
            enrollment={"status": "archived", "completed_steps": 0, "total_steps": 2},
        )

        self.assertEqual(payload["status"], "archived")
        self.assertEqual(payload["cta"], "Недоступно")
        self.assertEqual(payload["progress"]["percent"], 0)

    def test_program_card_payload_exposes_progress_and_next_action(self):
        payload = build_program_card_payload(
            program={
                "id": "program-1",
                "code": "trainee_base",
                "title": "Программа стажера GLAME",
                "description": "Базовая подготовка",
                "program_type": "trainee_base",
                "status": "active",
                "is_required": True,
                "order_index": 10,
            },
            enrollment={
                "status": "in_progress",
                "average_score": 7.25,
                "completed_steps": 3,
                "total_steps": 10,
                "pending_reviews": 0,
                "revision_count": 0,
            },
            next_assignment={"title": "Контакт с клиентом", "status": "not_opened"},
        )

        self.assertEqual(payload["status"], "in_progress")
        self.assertEqual(payload["progress"]["completed_steps"], 3)
        self.assertEqual(payload["progress"]["total_steps"], 10)
        self.assertEqual(payload["progress"]["percent"], 30)
        self.assertEqual(payload["average_score"], 7.25)
        self.assertEqual(payload["next_assignment"]["title"], "Контакт с клиентом")
        self.assertEqual(payload["cta"], "Продолжить")

    def test_program_structure_payload_groups_steps_and_locks_next_step(self):
        payload = build_program_structure_payload(
            program={"id": "program-1", "title": "Программа стажера GLAME", "code": "trainee_base"},
            modules=[
                {"id": "module-1", "title": "Сервис", "order_index": 10},
                {"id": "module-2", "title": "Продукт", "order_index": 20},
            ],
            steps=[
                {"id": "step-1", "module_id": "module-1", "title": "Приветствие", "order_index": 10, "is_required": True},
                {"id": "step-2", "module_id": "module-1", "title": "Контакт", "order_index": 20, "is_required": True},
                {"id": "step-3", "module_id": "module-2", "title": "Материалы", "order_index": 10, "is_required": True},
            ],
            step_progress={"step-1": {"status": "accepted", "score": 8}},
        )

        self.assertEqual(len(payload["modules"]), 2)
        service_steps = payload["modules"][0]["steps"]
        product_steps = payload["modules"][1]["steps"]
        self.assertEqual(service_steps[0]["status"], "accepted")
        self.assertEqual(service_steps[1]["status"], "available")
        self.assertEqual(product_steps[0]["status"], "locked")
        self.assertEqual(payload["progress"]["completed_steps"], 1)
        self.assertEqual(payload["progress"]["total_steps"], 3)
        self.assertEqual(payload["next_step"]["id"], "step-2")

    def test_current_learning_task_payload_prioritizes_next_assignment_and_hides_internal_data(self):
        payload = build_current_learning_task_payload(
            programs=[
                {
                    "id": "program-1",
                    "code": "trainee_base",
                    "title": "Программа стажера GLAME",
                    "status": "in_progress",
                    "progress": {"completed_steps": 1, "total_steps": 4, "percent": 25, "pending_reviews": 0, "revision_count": 0},
                    "next_assignment": {"id": "step-2", "title": "Первый контакт 30–60 секунд", "status": "available"},
                    "meta": {"internal_risk_flags": ["low_score"]},
                },
                {
                    "id": "program-2",
                    "code": "stylist_academy",
                    "title": "Программа стилиста GLAME",
                    "status": "locked",
                    "progress": {"completed_steps": 0, "total_steps": 4, "percent": 0},
                },
            ],
            daily_focus={"recommended_action": "Сегодня потренируйте мягкий первый контакт", "micro_practice": "Составьте одну GLAME-фразу"},
            competency_profile={"weakest_competencies": [{"code": "service_contact", "label": "Первый контакт", "percent": 20}]},
        )

        self.assertEqual(payload["primary_task"]["title"], "Первый контакт 30–60 секунд")
        self.assertEqual(payload["primary_task"]["cta"], "Продолжить обучение")
        self.assertEqual(payload["learning_flow"], ["lesson", "practice", "answer", "ai_review", "manager_review", "accepted_or_revision"])
        self.assertIn("AI-наставник", payload["mentor_prompt"])
        self.assertEqual(payload["knowledge_focus"]["code"], "service_contact")
        self.assertNotIn("internal_risk_flags", str(payload))

    def test_mentor_session_payload_routes_to_materials_before_practice(self):
        payload = build_training_mentor_session_payload(
            current_task={
                "primary_task": {
                    "program_id": "program-1",
                    "program_title": "Программа стажера GLAME",
                    "step_id": "step-1",
                    "title": "Миссия GLAME",
                    "status": "available",
                }
            },
            step_materials={
                "current_step": {
                    "id": "step-1",
                    "title": "Миссия GLAME",
                    "materials": [
                        {"material_id": "material-1", "title": "Урок о бренде", "required_to_complete": True}
                    ],
                    "practice_gate": {
                        "can_start_practice": False,
                        "next_action": "study_required_materials",
                        "blocked_materials": [{"material_id": "material-1", "title": "Урок о бренде"}],
                    },
                }
            },
        )

        self.assertEqual(payload["stage"], "materials")
        self.assertEqual(payload["material_id"], "material-1")
        self.assertEqual(payload["step_id"], "step-1")
        self.assertEqual(payload["next_action"], "continue_material")
        self.assertIn("Урок о бренде", payload["message"])
        self.assertNotIn("internal", str(payload).lower())

    def test_mentor_session_payload_routes_to_practice_when_gate_is_open(self):
        payload = build_training_mentor_session_payload(
            current_task={
                "primary_task": {
                    "program_id": "program-1",
                    "program_title": "Программа стажера GLAME",
                    "step_id": "step-1",
                    "title": "Миссия GLAME",
                    "status": "available",
                }
            },
            step_materials={
                "current_step": {
                    "id": "step-1",
                    "title": "Миссия GLAME",
                    "materials": [{"material_id": "material-1", "title": "Урок о бренде"}],
                    "practice_gate": {"can_start_practice": True, "next_action": "start_practice"},
                }
            },
        )

        self.assertEqual(payload["stage"], "practice")
        self.assertEqual(payload["next_action"], "start_practice")
        self.assertEqual(payload["step_id"], "step-1")
        self.assertIn("задание", payload["message"].lower())

    def test_mentor_session_payload_keeps_seller_in_materials_until_current_lesson_slides_completed(self):
        payload = build_training_mentor_session_payload(
            current_task={
                "primary_task": {
                    "program_id": "program-stylist",
                    "program_title": "Программа стилиста GLAME",
                    "step_id": "step-face-shape",
                    "title": "Эффект украшения на образ",
                    "status": "available",
                }
            },
            step_materials={
                "current_step": {
                    "id": "step-face-shape",
                    "title": "Эффект украшения на образ",
                    "materials": [{"material_id": "material-face-shape", "title": "Эффект украшения на образ", "required_to_complete": True}],
                    "practice_gate": {"can_start_practice": True, "next_action": "start_practice"},
                }
            },
            current_material={
                "id": "material-face-shape",
                "title": "Эффект украшения на образ",
                "program_id": "program-stylist",
                "step_id": "step-face-shape",
                "step_title": "Эффект украшения на образ",
                "progress": {"slides": 4, "completed_slides": 0, "progress_percent": 0, "material_completed": False},
            },
        )

        self.assertEqual(payload["stage"], "materials")
        self.assertEqual(payload["next_action"], "continue_material")
        self.assertEqual(payload["material_id"], "material-face-shape")
        self.assertIn("слайды", payload["message"].lower())
        self.assertEqual(payload["context"]["material_progress"]["completed_slides"], 0)
        self.assertNotIn("сразу открываю задание", payload["message"].lower())

    def test_mentor_session_payload_routes_to_review_and_waiting(self):
        review_payload = build_training_mentor_session_payload(
            current_task={"primary_task": {"title": "Первый контакт", "status": "submitted", "step_id": "step-2"}},
            step_materials={"current_step": None},
        )
        waiting_payload = build_training_mentor_session_payload(current_task={}, step_materials={"current_step": None})

        self.assertEqual(review_payload["stage"], "review")
        self.assertEqual(review_payload["next_action"], "wait_manager_review")
        self.assertEqual(waiting_payload["stage"], "waiting")
        self.assertEqual(waiting_payload["next_action"], "wait_assignment")

    def test_mentor_session_payload_uses_single_published_material_as_current_source(self):
        payload = build_training_mentor_session_payload(
            current_task={"primary_task": {"program_id": "program-stylist", "title": "Старая тема", "status": "available"}},
            step_materials={"current_step": None},
            current_material={
                "id": "material-ss26",
                "title": "Тренд SS26: крупная форма и металл как главный акцент образа",
                "program_id": "program-stylist",
                "step_id": "step-ss26",
                "step_title": "Тренд SS26: крупная форма и металл как главный акцент образа",
                "progress": {"slides": 10, "completed_slides": 0, "material_completed": False},
            },
        )

        self.assertEqual(payload["stage"], "materials")
        self.assertEqual(payload["material_id"], "material-ss26")
        self.assertEqual(payload["step_id"], "step-ss26")
        self.assertIn("SS26", payload["message"])
        self.assertNotIn("Старая тема", payload["message"])

    def test_current_learning_task_ignores_archived_program_when_stylist_assigned(self):
        payload = build_current_learning_task_payload(
            programs=[
                {"id": "p-trainee", "code": "trainee_base", "title": "Программа стажера GLAME", "status": "archived", "progress": {"completed_steps": 0, "total_steps": 2, "percent": 0}},
                {"id": "p-stylist", "code": "stylist_academy", "title": "Программа стилиста GLAME", "status": "available", "progress": {"completed_steps": 0, "total_steps": 1, "percent": 0}},
            ],
            daily_focus={},
            competency_profile={},
        )

        self.assertEqual(payload["primary_task"]["program_id"], "p-stylist")
        self.assertEqual(payload["primary_task"]["program_code"], "stylist_academy")
        self.assertEqual(payload["primary_task"]["program_title"], "Программа стилиста GLAME")

    def test_material_practice_assignment_is_concrete_methodical_task(self):
        payload = build_training_material_practice_assignment_payload(
            material={
                "id": "material-ss26",
                "title": "Тренд SS26: крупная форма и металл как главный акцент образа",
                "topic": "Тренды SS26",
            },
            step_title="Тренд SS26: крупная форма и металл как главный акцент образа",
        )

        self.assertIn("Что сделать", payload["task"])
        self.assertIn("5 украш", payload["task"])
        self.assertIn("Фраза", payload["answer_template"])
        self.assertIn("Можно примерить как один главный акцент", payload["try_phrase"])
        self.assertIn("Хороший ответ", payload["good_answer_example"])
        self.assertGreaterEqual(len(payload["assessment_criteria"]), 5)
        self.assertTrue(any("конкрет" in item.lower() for item in payload["assessment_criteria"]))
        self.assertTrue(any("GLAME" in item for item in payload["assessment_criteria"]))
        self.assertNotIn("internal", str(payload).lower())

    def test_mentor_session_payload_exposes_material_practice_assignment_when_ready(self):
        payload = build_training_mentor_session_payload(
            current_task={"primary_task": {"program_id": "program-stylist", "title": "Старая тема", "status": "available"}},
            step_materials={"current_step": None},
            current_material={
                "id": "material-ss26",
                "title": "Тренд SS26: крупная форма и металл как главный акцент образа",
                "topic": "Тренды SS26",
                "program_id": "program-stylist",
                "step_id": "step-ss26",
                "step_title": "Тренд SS26: крупная форма и металл как главный акцент образа",
                "progress": {"slides": 10, "completed_slides": 10, "material_completed": True},
            },
        )

        self.assertEqual(payload["stage"], "practice")
        self.assertEqual(payload["material_id"], "material-ss26")
        self.assertIn("practice_assignment", payload["context"])
        assignment = payload["context"]["practice_assignment"]
        self.assertIn("Что сделать", assignment["task"])
        self.assertIn("примерить", assignment["try_phrase"])
        self.assertIn("Хороший ответ", assignment["good_answer_example"])
        self.assertGreaterEqual(len(assignment["assessment_criteria"]), 5)

    def test_seller_career_level_payload_combines_learning_sales_and_salary_policy(self):
        payload = build_seller_career_level_payload(
            competency_profile={
                "level": "Стажер",
                "completed_steps": 2,
                "total_steps": 8,
                "average_score": 7.4,
                "attestation_ready": False,
                "achievements": [{"code": "glame_phrase", "title": "GLAME-фраза"}],
            },
            kpi_summary={"completion_percent": 62, "monthly_revenue": 180000, "avg_check": 6400},
            programs=[{"progress": {"pending_reviews": 1, "revision_count": 0}}],
        )

        self.assertEqual(payload["current_level"]["code"], "trainee")
        self.assertEqual(payload["next_level"]["code"], "junior")
        self.assertIn("знания", payload["score_breakdown"])
        self.assertIn("реальные продажи", payload["score_breakdown"])
        self.assertEqual(payload["salary_policy"]["status"], "pending_management_approval")
        self.assertIn("зарплат", payload["salary_policy"]["description"])
        self.assertGreater(len(payload["requirements_to_next_level"]), 0)
        self.assertNotIn("internal_risk_flags", str(payload))

    def test_team_career_levels_payload_gives_manager_level_distribution_and_actions(self):
        payload = build_team_career_levels_payload(
            seller_profiles=[
                {
                    "seller": {"full_name": "Анна", "email": "anna@example.test"},
                    "profile": {"level": "Стажер", "completed_steps": 2, "total_steps": 8, "average_score": 7.4, "attestation_ready": False},
                },
                {
                    "seller": {"full_name": "Мария", "email": "maria@example.test"},
                    "profile": {"level": "GLAME Stylist", "completed_steps": 8, "total_steps": 8, "average_score": 9.2, "attestation_ready": True},
                },
            ],
            kpi_sellers=[
                {"seller_name": "Анна", "completion_percent": 62, "monthly_revenue": 180000, "avg_check": 6400},
                {"seller_name": "Мария", "completion_percent": 112, "monthly_revenue": 420000, "avg_check": 9800},
            ],
        )

        self.assertEqual(payload["salary_policy"]["status"], "pending_management_approval")
        self.assertIn("зарплат", payload["salary_policy"]["description"])
        self.assertGreaterEqual(payload["summary"]["total_sellers"], 2)
        self.assertIn("level_distribution", payload["summary"])
        self.assertEqual(payload["sellers"][0]["seller"]["full_name"], "Анна")
        self.assertIn("career_level", payload["sellers"][0])
        self.assertIn("manager_next_action", payload["sellers"][0])
        self.assertNotIn("salary_amount", str(payload))
        self.assertNotIn("bonus_formula", str(payload))

    def test_step_submission_status_normalization_is_review_safe(self):
        self.assertEqual(normalize_step_submission_status("review_pending"), "review_pending")
        self.assertEqual(normalize_step_submission_status("revision_requested"), "revision_requested")
        self.assertEqual(normalize_step_submission_status("accepted"), "accepted")
        self.assertEqual(normalize_step_submission_status("unexpected"), "review_pending")

    def test_step_submission_payload_keeps_ai_feedback_as_manager_draft(self):
        payload = build_step_submission_payload(
            submission={
                "id": "submission-1",
                "program_id": "program-1",
                "step_id": "step-1",
                "seller_user_id": "seller-1",
                "practice_answer": "Ответ продавца",
                "ai_score": 4,
                "ai_evaluation": {"recommendation": "request_revision", "review_comment": "Доработайте конкретику"},
                "review_status": "revision_draft",
                "consultant_feedback": "Пока не показывать продавцу",
            },
            step={"id": "step-1", "title": "Первый контакт", "competencies": ["service_contact"]},
            include_internal=True,
        )

        self.assertEqual(payload["step_title"], "Первый контакт")
        self.assertEqual(payload["status"], "revision_draft")
        self.assertEqual(payload["ai_score"], 4)
        self.assertIn("ai_evaluation", payload)
        self.assertEqual(payload["consultant_feedback"], "Пока не показывать продавцу")

        seller_payload = build_step_submission_payload(
            submission=payload,
            step={"id": "step-1", "title": "Первый контакт", "competencies": ["service_contact"]},
            include_internal=False,
        )
        self.assertNotIn("ai_evaluation", seller_payload)
        self.assertIsNone(seller_payload["consultant_feedback"])

    def test_apply_step_submission_progress_marks_pending_and_acceptance(self):
        pending = apply_step_submission_progress(
            current_meta={},
            step_id="step-1",
            submission_id="submission-1",
            review_status="review_pending",
            ai_score=7,
        )
        self.assertEqual(pending["step_progress"]["step-1"]["status"], "submitted")
        self.assertEqual(pending["step_progress"]["step-1"]["submission_id"], "submission-1")
        self.assertEqual(pending["step_progress"]["step-1"]["score"], 7)

        accepted = apply_step_submission_progress(
            current_meta=pending,
            step_id="step-1",
            submission_id="submission-1",
            review_status="accepted",
            ai_score=9,
        )
        self.assertEqual(accepted["step_progress"]["step-1"]["status"], "accepted")
        self.assertEqual(accepted["step_progress"]["step-1"]["score"], 9)
    def test_competency_profile_calculates_levels_and_achievements(self):
        payload = build_competency_profile_payload(
            steps=[
                {"id": "step-1", "competencies": ["service_contact", "glame_language"]},
                {"id": "step-2", "competencies": ["service_contact", "product_knowledge"]},
                {"id": "step-3", "competencies": ["styling_effect", "glame_language"]},
            ],
            step_progress={
                "step-1": {"status": "accepted", "score": 9},
                "step-2": {"status": "accepted", "score": 8},
                "step-3": {"status": "needs_revision", "score": 4},
            },
        )

        self.assertEqual(payload["level"], "Junior Consultant")
        self.assertEqual(payload["completed_steps"], 2)
        self.assertEqual(payload["competencies"]["service_contact"]["accepted_steps"], 2)
        self.assertEqual(payload["competencies"]["service_contact"]["percent"], 100)
        self.assertLess(payload["competencies"]["styling_effect"]["percent"], 100)
        achievement_codes = [item["code"] for item in payload["achievements"]]
        self.assertIn("first_step", achievement_codes)
        self.assertIn("service_foundation", achievement_codes)
        self.assertIn("high_quality_answers", achievement_codes)
        self.assertEqual(payload["weakest_competencies"][0]["code"], "styling_effect")

    def test_attestation_payload_respects_readiness_and_manager_decision(self):
        self.assertEqual(normalize_attestation_status("certified"), "certified")
        self.assertEqual(normalize_attestation_status("bad"), "draft")
        competency_profile = {"attestation_ready": True, "level": "Junior Consultant", "average_score": 8.5}
        payload = build_attestation_payload(
            attestation={
                "id": "att-1",
                "program_id": "program-1",
                "seller_user_id": "seller-1",
                "attestation_type": "trainee_final",
                "status": "review_pending",
                "ai_score": 8,
                "ai_evaluation": {"recommendation": "accept"},
                "manager_decision": None,
            },
            competency_profile=competency_profile,
            include_internal=True,
        )
        self.assertTrue(payload["eligible"])
        self.assertEqual(payload["recommended_level"], "Junior Consultant")
        self.assertIn("ai_evaluation", payload)
        seller_payload = build_attestation_payload(attestation=payload, competency_profile=competency_profile, include_internal=False)
        self.assertNotIn("ai_evaluation", seller_payload)

    def test_mentor_reply_guides_without_final_grading_or_manager_bypass(self):
        self.assertEqual(normalize_mentor_message_role("mentor"), "mentor")
        self.assertEqual(normalize_mentor_message_role("manager"), "user")

        reply = build_mentor_reply(
            question="Проверь мой ответ и скажи, сдаю ли я аттестацию?",
            context={"program_title": "Программа стилиста GLAME", "step_title": "Эффект украшения на образ"},
            competency_profile={"weakest_competencies": [{"label": "Эффект украшения на образ"}]},
        )

        self.assertEqual(reply["sender_role"], "mentor")
        self.assertTrue(reply["requires_manager_review"])
        self.assertIn("руковод", reply["response_text"].lower())
        self.assertNotIn("аттестация сдана", reply["response_text"].lower())
        self.assertIn("Эффект украшения на образ", reply["focus_tags"])

    def test_mentor_message_payload_hides_internal_flags_from_seller(self):
        message = {
            "id": "msg-1",
            "seller_user_id": "seller-1",
            "sender_role": "mentor",
            "question_text": "Как сказать клиенту мягче?",
            "response_text": "Попробуйте через эффект на образ.",
            "context": {"program_id": "program-1"},
            "risk_flags": ["needs_manager_review"],
        }
        admin_payload = build_mentor_message_payload(message, include_internal=True)
        seller_payload = build_mentor_message_payload(message, include_internal=False)

        self.assertIn("risk_flags", admin_payload)
        self.assertNotIn("risk_flags", seller_payload)
        self.assertEqual(seller_payload["response_text"], "Попробуйте через эффект на образ.")

    def test_management_analytics_payload_highlights_risks_and_recommendations(self):
        payload = build_management_analytics_payload(
            seller_profiles=[
                {"seller": {"id": "seller-1", "full_name": "Анна"}, "profile": {"completed_steps": 0, "total_steps": 6, "attestation_ready": False, "weakest_competencies": [{"code": "service_contact", "label": "Первый контакт", "percent": 0}]}},
                {"seller": {"id": "seller-2", "full_name": "Мария"}, "profile": {"completed_steps": 5, "total_steps": 6, "attestation_ready": True, "weakest_competencies": [{"code": "styling_effect", "label": "Эффект на образ", "percent": 50}]}},
            ],
            step_submissions=[
                {"review_status": "review_pending", "step_title": "Контакт"},
                {"review_status": "revision_requested", "step_title": "Контакт"},
                {"review_status": "accepted", "step_title": "Материалы"},
            ],
            mentor_messages=[
                {"risk_flags": ["needs_manager_review"], "context": {"focus_tags": ["Эффект на образ"]}},
                {"risk_flags": [], "context": {"focus_tags": ["Эффект на образ", "GLAME-фраза"]}},
            ],
            attestations=[{"status": "review_pending"}, {"status": "certified"}],
        )

        self.assertEqual(payload["summary"]["active_learners"], 2)
        self.assertEqual(payload["summary"]["zero_progress"], 1)
        self.assertEqual(payload["summary"]["pending_reviews"], 2)
        self.assertEqual(payload["summary"]["attestation_ready"], 1)
        self.assertEqual(payload["submission_bottlenecks"][0]["step_title"], "Контакт")
        self.assertEqual(payload["mentor_focus_tags"][0]["tag"], "Эффект на образ")
        self.assertTrue(payload["risk_sellers"])
        self.assertTrue(payload["recommendations"])

    def test_training_kpi_linkage_payload_prioritizes_learning_actions_for_low_kpi(self):
        payload = build_training_kpi_linkage_payload(
            seller_profiles=[
                {
                    "seller": {"id": "seller-1", "full_name": "Анна Смирнова", "email": "anna@example.com"},
                    "profile": {
                        "level": "Стажер",
                        "completed_steps": 1,
                        "total_steps": 8,
                        "attestation_ready": False,
                        "weakest_competencies": [{"code": "service_contact", "label": "Первый контакт", "percent": 25}],
                    },
                },
                {
                    "seller": {"id": "seller-2", "full_name": "Мария Иванова", "email": "maria@example.com"},
                    "profile": {
                        "level": "Styлист GLAME",
                        "completed_steps": 7,
                        "total_steps": 8,
                        "attestation_ready": True,
                        "weakest_competencies": [],
                    },
                },
            ],
            kpi_sellers=[
                {"seller_name": "Анна Смирнова", "store_name": "ТРК Центрум", "revenue": 90000, "revenue_plan": 180000, "completion_percent": 50, "avg_check": 3500, "items_per_check": 1.1, "checks": 20},
                {"seller_name": "Мария Иванова", "store_name": "ТРК Центрум", "revenue": 210000, "revenue_plan": 200000, "completion_percent": 105, "avg_check": 7600, "items_per_check": 1.8, "checks": 32},
            ],
        )

        self.assertEqual(payload["summary"]["matched_sellers"], 2)
        self.assertEqual(payload["summary"]["low_kpi_and_low_training"], 1)
        self.assertLess(payload["summary"]["avg_completion_low_training"], payload["summary"]["avg_completion_trained"])
        self.assertEqual(payload["seller_actions"][0]["seller"]["full_name"], "Анна Смирнова")
        self.assertEqual(payload["seller_actions"][0]["priority"], "high")
        self.assertIn("Первый контакт", payload["seller_actions"][0]["recommended_training_focus"])
        self.assertTrue(payload["recommendations"])

    def test_seller_training_account_preferences_update_keeps_mapping_audit(self):
        updated = build_seller_training_account_preferences_update(
            current_preferences={"theme": "dark", "seller_external_id": "old-id"},
            seller_external_id="1c-anna",
            seller_name="Анна Смирнова",
            store_name="ТРК Центрум",
            manager_user_id="manager-1",
        )

        self.assertEqual(updated["theme"], "dark")
        self.assertEqual(updated["seller_external_id"], "1c-anna")
        self.assertEqual(updated["onec_seller_id"], "1c-anna")
        self.assertEqual(updated["seller_name"], "Анна Смирнова")
        self.assertEqual(updated["seller_store_name"], "ТРК Центрум")
        self.assertEqual(updated["training_account_mapping"]["mapped_by_user_id"], "manager-1")
        self.assertEqual(updated["training_account_mapping"]["previous_seller_external_id"], "old-id")
        self.assertIn("mapped_at", updated["training_account_mapping"])

    def test_seller_daily_training_focus_payload_is_supportive_and_actionable(self):
        payload = build_seller_daily_training_focus_payload(
            seller={"full_name": "Анна Смирнова", "preferences": {"seller_store_name": "ТРК Центрум"}},
            training_summary={
                "level": "Стажер",
                "progress_percent": 25,
                "recommended_training_focus": "Первый контакт и сервис",
                "kpi_focus": ["средний чек", "изделий в чеке"],
                "next_program_title": "Программа стажера GLAME",
                "next_action": {"title": "Первый контакт 30–60 секунд", "id": "step-2"},
                "weakest_competencies": [{"label": "Первый контакт и сервис", "percent": 25}],
                "priority": "high",
            },
            kpi={"completion_percent": 62, "avg_check": 4200, "items_per_check": 1.1, "revenue": 90000, "revenue_plan": 145000},
        )

        self.assertEqual(payload["priority"], "high")
        self.assertEqual(payload["today_focus"]["metric"], "средний чек")
        self.assertIn("Первый контакт", payload["training_step"]["title"])
        self.assertIn("комплект", payload["recommended_action"].lower())
        self.assertNotIn("плохо", payload["tone_guardrails"].lower())
        self.assertTrue(payload["mentor_prompt"])

    def test_schedule_aware_training_focus_uses_today_shift_before_shift_mode(self):
        base_focus = {
            "priority": "high",
            "recommended_action": "Сегодня тренируем спокойное предложение комплекта.",
            "micro_practice": "Перед сменой проговорите GLAME-фразу.",
            "today_focus": {"metric": "средний чек", "training_competency": "Первый контакт"},
        }
        payload = build_schedule_aware_training_focus_payload(
            daily_focus=base_focus,
            shifts=[{"date": "2026-06-01", "store_name": "ТРК Центрум", "start_time": "10:00", "end_time": "19:00"}],
            today="2026-06-01",
            current_time="09:20",
        )

        self.assertEqual(payload["schedule_context"]["mode"], "before_shift")
        self.assertEqual(payload["schedule_context"]["nearest_shift"]["store_name"], "ТРК Центрум")
        self.assertIn("перед сменой", payload["schedule_context"]["title"].lower())
        self.assertIn("10:00", payload["micro_practice"])
        self.assertIn("ТРК Центрум", payload["recommended_action"])

    def test_schedule_aware_training_focus_gives_light_preparation_without_shift(self):
        payload = build_schedule_aware_training_focus_payload(
            daily_focus={"recommended_action": "Закрепите GLAME-фразу.", "micro_practice": "5 минут практики."},
            shifts=[],
            today="2026-06-01",
        )

        self.assertEqual(payload["schedule_context"]["mode"], "no_shift")
        self.assertIn("легкая подготовка", payload["schedule_context"]["title"].lower())

    def test_shift_reflection_payload_highlights_coaching_risks_without_shaming(self):
        payload = build_shift_reflection_payload(
            reflection={
                "worked_well": "Получилось начать диалог мягко и показать комплект",
                "difficult_scenario": "Сложно объяснять цену и клиент сомневался",
                "glame_argument": "Украшение собирает образ и добавляет акцент",
                "needs_help": "Нужна помощь с возражением дорого",
            },
            daily_focus={"today_focus": {"metric": "средний чек", "training_competency": "Первый контакт"}, "training_step": {"title": "Первый контакт 30–60 секунд"}},
        )

        self.assertEqual(payload["status"], "needs_coaching")
        self.assertIn("price_objection", payload["risk_flags"])
        self.assertIn("Первый контакт", payload["competency_links"])
        self.assertIn("руковод", payload["manager_note"].lower())
        self.assertNotIn("плохо", payload["seller_feedback"].lower())

    def test_shift_reflection_payload_accepts_positive_reflection(self):
        payload = build_shift_reflection_payload(
            reflection={
                "worked_well": "Клиентке подошел комплект, я объяснила эффект на образ и она взяла серьги с кольцом",
                "difficult_scenario": "Сложностей не было",
                "glame_argument": "Комплект делает образ цельным",
                "needs_help": "",
            },
            daily_focus={"today_focus": {"metric": "изделий в чеке", "training_competency": "Комплектность"}},
        )

        self.assertEqual(payload["status"], "completed")
        self.assertFalse(payload["risk_flags"])
        self.assertGreaterEqual(payload["ai_score"], 7)

    def test_coaching_action_payload_turns_reflection_risk_into_manager_task(self):
        payload = build_coaching_action_payload(
            reflection={
                "id": "reflection-1",
                "seller_user_id": "seller-1",
                "store_name": "ТРК Центрум",
                "shift_date": "2026-06-01",
                "risk_flags": ["price_objection", "asked_for_help"],
                "manager_note": "Руководителю: разобрать возражение по цене",
                "ai_evaluation": {"competency_links": ["Первый контакт"], "kpi_metric": "средний чек"},
            },
            manager_user_id="manager-1",
            planned_for="2026-06-02",
        )

        self.assertEqual(payload["status"], "planned")
        self.assertEqual(payload["seller_user_id"], "seller-1")
        self.assertEqual(payload["reflection_id"], "reflection-1")
        self.assertEqual(payload["competency"], "Первый контакт")
        self.assertEqual(payload["kpi_metric"], "средний чек")
        self.assertIn("цен", payload["coaching_topic"].lower())
        self.assertIn("GLAME", payload["manager_script"])
        self.assertNotIn("плохо", payload["seller_next_step"].lower())
        self.assertEqual(payload["created_by_user_id"], "manager-1")

    def test_coaching_action_status_normalization_keeps_safe_flow(self):
        self.assertEqual(normalize_coaching_action_status("planned"), "planned")
        self.assertEqual(normalize_coaching_action_status("discussed"), "discussed")
        self.assertEqual(normalize_coaching_action_status("resolved"), "resolved")
        self.assertEqual(normalize_coaching_action_status("bad"), "new")

    def test_training_material_payload_keeps_markdown_and_seller_safe_status(self):
        payload = build_training_material_payload(
            {
                "id": "material-1",
                "title": "Первый контакт 30–60 секунд",
                "topic": "Сервис",
                "category": "База стажера",
                "markdown_content": "# Первый контакт\n\nСкажите клиенту мягкую GLAME-фразу.",
                "status": "published",
                "tags": ["первый контакт", "сервис"],
                "source_type": "trainee_workbook",
                "order_index": 20,
            },
            include_internal=False,
        )

        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["content_format"], "markdown")
        self.assertIn("# Первый контакт", payload["markdown_content"])
        self.assertEqual(payload["topic"], "Сервис")
        self.assertNotIn("internal_notes", payload)
        self.assertEqual(normalize_training_material_status("bad"), "draft")

    def test_training_material_payload_keeps_source_file_admin_only(self):
        imported = parse_training_material_document_import(
            filename="GLAME_face_shape.pdf",
            content_base64=base64.b64encode(b"Face shape training source PDF text layer").decode("ascii"),
            mime_type="application/pdf",
            default_topic="Стилистический подбор",
        )
        admin_payload = build_training_material_payload({"id": "m-source", **imported}, include_internal=True)
        seller_payload = build_training_material_payload({"id": "m-source", **imported, "status": "published"}, include_internal=False)

        self.assertEqual(admin_payload["source_file"]["filename"], "GLAME_face_shape.pdf")
        self.assertEqual(admin_payload["source_file"]["mime_type"], "application/pdf")
        self.assertTrue(admin_payload["source_file"]["has_content"])
        self.assertNotIn("content_base64", admin_payload["source_file"])
        self.assertNotIn("source_file", seller_payload)

    def test_training_material_source_file_payload_can_include_content_for_download(self):
        imported = parse_training_material_document_import(
            filename="lesson.txt",
            content="Исходный текст урока GLAME",
            mime_type="text/plain",
        )
        source_file = build_training_material_source_file_payload(imported["extraction_metadata"], include_content=True)

        self.assertEqual(source_file["filename"], "lesson.txt")
        self.assertEqual(base64.b64decode(source_file["content_base64"]).decode("utf-8"), "Исходный текст урока GLAME")

    def test_import_agent_recognizes_metadata_from_source_text(self):
        material = {
            "title": "Концепция бренда GLAME",
            "topic": "Общее",
            "category": "Импорт документов",
            "markdown_content": "# Концепция бренда GLAME\n\nПремиальный сервис, ценности бренда, стандарты коммуникации и первый контакт с клиентом.",
            "tags": [],
            "competencies": [],
            "extraction_metadata": {"quality": "ok", "warnings": []},
        }

        enriched = enrich_training_material_import_metadata(material, default_program_code="trainee_base")

        self.assertEqual(enriched["program_code"], "trainee_base")
        self.assertEqual(enriched["topic"], "База продаж: сервис и стандарты")
        self.assertEqual(enriched["category"], "Программа стажера GLAME")
        self.assertIn("сервис", enriched["tags"])
        self.assertIn("первый контакт", enriched["competencies"])
        self.assertIn("auto_recognized", enriched["extraction_metadata"])

    def test_bulk_import_auto_builds_complete_material_payload(self):
        payload = build_training_material_bulk_import_payload(
            files=[{"filename": "concept.txt", "content": "Концепция бренда GLAME\n\nПервый контакт, сервис, ценности бренда и коммуникация с клиентом."}],
            default_program_code="trainee_base",
        )

        material = payload["materials"][0]
        self.assertEqual(material["program_code"], "trainee_base")
        self.assertEqual(material["topic"], "База продаж: сервис и стандарты")
        self.assertEqual(material["category"], "Программа стажера GLAME")
        self.assertTrue(material["tags"])
        self.assertTrue(material["competencies"])

    def test_training_material_library_payload_groups_published_materials_by_topic(self):
        payload = build_training_material_library_payload(
            [
                {"id": "m1", "title": "Первый контакт", "topic": "Сервис", "status": "published", "markdown_content": "# 1", "order_index": 20},
                {"id": "m2", "title": "Материалы", "topic": "Продукт", "status": "published", "markdown_content": "# 2", "order_index": 10},
                {"id": "m3", "title": "Черновик", "topic": "Сервис", "status": "draft", "markdown_content": "# draft", "order_index": 5},
            ],
            seller_view=True,
        )

        self.assertEqual(payload["summary"]["total_materials"], 2)
        self.assertEqual([group["topic"] for group in payload["topics"]], ["Продукт", "Сервис"])
        self.assertEqual(payload["topics"][1]["materials"][0]["title"], "Первый контакт")
        self.assertNotIn("Черновик", str(payload))

    def test_training_material_search_payload_filters_published_by_query_and_topic(self):
        payload = build_training_material_search_payload(
            [
                {"id": "m1", "title": "Первый контакт", "topic": "Сервис", "category": "База", "status": "published", "markdown_content": "# Контакт\nМягкая GLAME-фраза", "tags": ["сервис"]},
                {"id": "m2", "title": "Камни и материалы", "topic": "Продукт", "category": "База", "status": "published", "markdown_content": "# Камни\nКак объяснять материал", "tags": ["продукт"]},
                {"id": "m3", "title": "Черновик сервиса", "topic": "Сервис", "category": "База", "status": "draft", "markdown_content": "# draft"},
            ],
            query="GLAME-фраза",
            topic="Сервис",
            seller_view=True,
        )

        self.assertEqual(payload["summary"]["total_matches"], 1)
        self.assertEqual(payload["materials"][0]["id"], "m1")
        self.assertIn("GLAME-фраза", payload["materials"][0]["snippet"])
        self.assertNotIn("Черновик", str(payload))

    def test_training_material_context_payload_selects_limited_markdown_for_ai_mentor(self):
        payload = build_training_material_context_payload(
            [
                {"id": "m1", "title": "Первый контакт", "topic": "Сервис", "status": "published", "markdown_content": "# Контакт\n" + "Фраза клиента. " * 80, "tags": ["сервис"]},
                {"id": "m2", "title": "Материалы", "topic": "Продукт", "status": "published", "markdown_content": "# Материалы\nКамни и уход", "tags": ["продукт"]},
                {"id": "m3", "title": "Внутренний черновик", "topic": "Сервис", "status": "draft", "markdown_content": "# Нельзя продавцу"},
            ],
            query="как начать контакт с клиентом",
            competency="Первый контакт",
            max_materials=1,
            max_chars=220,
        )

        self.assertEqual(payload["summary"]["selected_materials"], 1)
        self.assertEqual(payload["materials"][0]["title"], "Первый контакт")
        self.assertLessEqual(len(payload["context_markdown"]), 260)
        self.assertNotIn("Внутренний черновик", payload["context_markdown"])

    def test_mentor_reply_with_library_context_cites_published_materials(self):
        library_context = build_training_material_context_payload(
            [
                {"id": "m1", "title": "Первый контакт", "topic": "Сервис", "status": "published", "markdown_content": "# Первый контакт\nИспользуйте мягкую GLAME-фразу без давления.", "tags": ["сервис"]},
                {"id": "m2", "title": "Черновик", "topic": "Сервис", "status": "draft", "markdown_content": "# Черновик"},
            ],
            query="как начать разговор",
            competency="Первый контакт",
        )

        reply = build_mentor_reply_with_library_context(
            question="Как начать разговор с клиентом?",
            context={"step_title": "Первый контакт"},
            competency_profile={"weakest_competencies": [{"label": "Первый контакт", "percent": 30}]},
            library_context=library_context,
        )

        self.assertIn("Источник библиотеки GLAME", reply["response_text"])
        self.assertEqual(reply["source_materials"][0]["title"], "Первый контакт")
        self.assertEqual(reply["context"]["library_context"]["selected_materials"], 1)
        self.assertNotIn("Черновик", str(reply))

    def test_parse_training_material_markdown_import_reads_frontmatter_and_heading(self):
        payload = parse_training_material_markdown_import(
            filename="service/first-contact.md",
            content="""---
title: Первый контакт 30 секунд
topic: Сервис
category: База стажера
tags: первый контакт, сервис
program_code: trainee_base
competencies: Первый контакт, GLAME-язык
status: review
order_index: 15
---
# Первый контакт

Скажите клиенту мягкую GLAME-фразу без давления.
""",
        )

        self.assertEqual(payload["title"], "Первый контакт 30 секунд")
        self.assertEqual(payload["topic"], "Сервис")
        self.assertEqual(payload["category"], "База стажера")
        self.assertEqual(payload["tags"], ["первый контакт", "сервис"])
        self.assertEqual(payload["competencies"], ["Первый контакт", "GLAME-язык"])
        self.assertEqual(payload["status"], "review")
        self.assertEqual(payload["order_index"], 15)
        self.assertIn("# Первый контакт", payload["markdown_content"])

    def test_training_material_bulk_import_payload_skips_empty_and_duplicates(self):
        payload = build_training_material_bulk_import_payload(
            files=[
                {"filename": "service/first-contact.md", "content": "# Первый контакт\n\nТекст"},
                {"filename": "service/first-contact-copy.md", "content": "# Первый контакт\n\nДубль"},
                {"filename": "empty.md", "content": "   "},
                {"filename": "product/materials.md", "content": "---\ntopic: Продукт\n---\n# Материалы\n\nТекст"},
            ],
            default_topic="Общее",
            default_category="Импорт .md",
            default_status="draft",
        )

        self.assertEqual(payload["summary"]["total_files"], 4)
        self.assertEqual(payload["summary"]["ready_to_import"], 2)
        self.assertEqual(payload["summary"]["skipped"], 2)
        self.assertEqual([item["title"] for item in payload["materials"]], ["Первый контакт", "Материалы"])
        self.assertEqual(payload["materials"][0]["category"], "Импорт .md")
        self.assertTrue(any(item["reason"] == "duplicate_title" for item in payload["skipped_files"]))

    def test_parse_training_material_document_import_reads_txt_and_marks_source(self):
        payload = parse_training_material_document_import(
            filename="База стажера/contact.txt",
            content="Первый контакт\n\nМягко поприветствуйте клиента и предложите помощь без давления.",
            default_topic="Сервис",
            default_category="Импорт документов",
        )

        self.assertEqual(payload["title"], "Первый контакт")
        self.assertEqual(payload["topic"], "Сервис")
        self.assertEqual(payload["category"], "Импорт документов")
        self.assertEqual(payload["source_type"], "txt_import")
        self.assertIn("Мягко поприветствуйте", payload["markdown_content"])
        self.assertIn("Исходный файл", payload["internal_notes"])

    def test_parse_training_material_document_import_extracts_docx_text_from_base64(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>
<w:p><w:r><w:t>GLAME язык</w:t></w:r></w:p>
<w:p><w:r><w:t>Говорим спокойно, без давления, через эффект украшения на образ.</w:t></w:r></w:p>
</w:body></w:document>""",
            )
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        payload = parse_training_material_document_import(
            filename="glame-language.docx",
            content_base64=encoded,
            default_topic="GLAME-язык",
            default_category="Импорт документов",
        )

        self.assertEqual(payload["title"], "GLAME язык")
        self.assertEqual(payload["source_type"], "docx_import")
        self.assertIn("Говорим спокойно", payload["markdown_content"])

    def test_training_material_bulk_import_payload_accepts_mixed_document_formats(self):
        payload = build_training_material_bulk_import_payload(
            files=[
                {"filename": "lesson.md", "content": "# Markdown урок\n\nТекст"},
                {"filename": "service.txt", "content": "Сервисный урок\n\nТекст из txt"},
                {"filename": "empty.pdf", "content_base64": ""},
                {"filename": "legacy.exe", "content": "bad"},
            ],
            default_topic="Общее",
            default_category="Импорт документов",
            default_status="draft",
        )

        self.assertEqual(payload["summary"]["total_files"], 4)
        self.assertEqual(payload["summary"]["ready_to_import"], 2)
        self.assertEqual(payload["materials"][1]["source_type"], "txt_import")
        self.assertTrue(any(item["reason"] == "empty_file" for item in payload["skipped_files"]))
        self.assertTrue(any(item["reason"] == "unsupported_format" for item in payload["skipped_files"]))

    def test_training_document_extraction_diagnostics_flags_scanned_pdf_for_ocr(self):
        diagnostics = build_training_document_extraction_diagnostics(
            filename="scan.pdf",
            extracted_text="   ",
            pages=3,
            extractor="pymupdf",
        )

        self.assertEqual(diagnostics["quality"], "needs_ocr")
        self.assertTrue(diagnostics["ocr_required"])
        self.assertIn("ocr_required", diagnostics["warnings"])
        self.assertIn("скан", diagnostics["manager_note"].lower())

    def test_document_import_visual_assets_are_admin_only_and_pending_review(self):
        payload = parse_training_material_document_import(
            filename="visual-example.pdf",
            content_base64=base64.b64encode(b"%PDF-1.4\nno real image").decode("ascii"),
            default_topic="Стилистика",
            default_category="Импорт документов",
        )
        extraction = payload["extraction_metadata"]
        extraction["visual_assets"] = [
            {
                "asset_id": "pdf-image-1",
                "filename": "visual-example-page-1-image-1.jpeg",
                "mime_type": "image/jpeg",
                "extension": "jpeg",
                "page": 1,
                "width": 640,
                "height": 800,
                "size_bytes": 120000,
                "content_base64": base64.b64encode(b"fake-image").decode("ascii"),
                "status": "pending_review",
                "source": "pdf_embedded_image",
                "admin_only": True,
            }
        ]

        admin_material = build_training_material_payload({**payload, "id": "m1", "status": "draft"}, include_internal=True)
        seller_material = build_training_material_payload({**payload, "id": "m1", "status": "published"}, include_internal=False)

        self.assertEqual(admin_material["visual_assets"][0]["status"], "pending_review")
        self.assertTrue(admin_material["visual_assets"][0]["admin_only"])
        self.assertNotIn("content_base64", admin_material["visual_assets"][0])
        self.assertNotIn("visual_assets", seller_material)
        self.assertNotIn("fake-image", str(seller_material))

    def test_visual_asset_update_requires_approval_before_slide_attachment(self):
        extraction = {
            "visual_assets": [
                {"asset_id": "a1", "filename": "look.jpeg", "status": "pending_review", "content_base64": base64.b64encode(b"image").decode("ascii"), "mime_type": "image/jpeg"},
                {"asset_id": "a2", "filename": "diagram.png", "status": "rejected"},
            ]
        }

        updated = build_training_material_visual_asset_update_payload(
            extraction,
            asset_id="a1",
            status="approved",
            note="Подходит для слайда о форме лица",
            slide_id="slide-1",
            reviewed_by_user_id="manager-1",
        )

        asset = updated["visual_assets"][0]
        self.assertEqual(asset["status"], "approved")
        self.assertEqual(asset["attached_slide_id"], "slide-1")
        self.assertEqual(asset["reviewed_by_user_id"], "manager-1")
        self.assertTrue(updated["visual_assets_summary"]["approved"])

    def test_extract_training_pdf_visual_assets_deduplicates_embedded_images_when_pymupdf_available(self):
        try:
            import fitz  # type: ignore
        except Exception:
            self.skipTest("PyMuPDF is optional in this environment")
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pix.clear_with(0xCCAA88)
        image_bytes = pix.tobytes("png")
        page.insert_image(fitz.Rect(10, 10, 90, 90), stream=image_bytes)
        page.insert_image(fitz.Rect(100, 10, 180, 90), stream=image_bytes)
        pdf_bytes = doc.tobytes()
        doc.close()

        assets = extract_training_pdf_visual_assets(pdf_bytes, filename="lesson.pdf")

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["page"], 1)
        self.assertEqual(assets[0]["status"], "pending_review")
        self.assertTrue(assets[0]["admin_only"])
        self.assertIn("content_base64", assets[0])

    def test_parse_training_material_document_import_adds_quality_metadata_and_manager_note(self):
        payload = parse_training_material_document_import(
            filename="short.pdf",
            content_base64=base64.b64encode(b"%PDF-1.4\nno readable text").decode("ascii"),
            default_topic="Продукт",
            default_category="Импорт документов",
        )

        self.assertEqual(payload["source_type"], "pdf_import")
        self.assertIn("extraction", payload)
        self.assertIn(payload["extraction"]["quality"], {"needs_ocr", "low"})
        self.assertIn("Проверьте качество извлечения", payload["internal_notes"])

    def test_bulk_import_summary_counts_extraction_warnings(self):
        payload = build_training_material_bulk_import_payload(
            files=[
                {"filename": "scan.pdf", "content_base64": base64.b64encode(b"%PDF-1.4\n").decode("ascii")},
                {"filename": "contact.txt", "content": "Первый контакт\n\nДостаточный учебный текст для проверки качества извлечения."},
            ],
            default_topic="Общее",
            default_category="Импорт документов",
            default_status="draft",
        )

        self.assertEqual(payload["summary"]["ready_to_import"], 2)
        self.assertGreaterEqual(payload["summary"]["warnings"], 1)
        self.assertTrue(payload["materials"][0]["extraction"]["warnings"])

    def test_document_extractor_status_payload_reports_safe_optional_tools(self):
        payload = build_document_extractor_status_payload(
            python_modules={"fitz": True, "pymupdf4llm": False, "marker": False},
            commands={"soffice": False, "antiword": True, "tesseract": False},
            free_disk_gb=8.5,
        )

        self.assertTrue(payload["extractors"]["pymupdf"]["available"])
        self.assertFalse(payload["extractors"]["marker_pdf"]["available"])
        self.assertEqual(payload["recommendation"], "lightweight_text_extraction_ready")
        self.assertIn("doc", payload["supported_extensions"])
        self.assertTrue(payload["warnings"])

    def test_training_material_retry_extraction_payload_applies_better_text_as_reviewed_draft(self):
        payload = build_training_material_retry_extraction_payload(
            material={
                "id": "m1",
                "title": "Скан PDF",
                "markdown_content": "# Скан PDF\n\nТекст не извлечен автоматически.",
                "internal_notes": "Исходный файл: scan.pdf.",
                "extraction_metadata": {"quality": "needs_ocr", "ocr_required": True, "warnings": ["ocr_required"]},
            },
            filename="scan.pdf",
            extracted_text="Проверенный OCR текст про первый контакт GLAME и правильную фразу консультанта.",
            extractor="manual_ocr_upload",
            reviewed_by_user_id="manager-1",
        )

        self.assertIn("Проверенный OCR текст", payload["markdown_content"])
        self.assertEqual(payload["extraction_metadata"]["quality"], "reviewed")
        self.assertEqual(payload["extraction_metadata"]["retry_extractor"], "manual_ocr_upload")
        self.assertFalse(payload["publish_gate"]["can_publish"] is False)

    def test_training_material_publish_gate_blocks_ocr_needed_import_until_reviewed(self):
        gate = build_training_material_publish_gate_payload(
            {
                "id": "m1",
                "title": "Скан PDF",
                "status": "review",
                "extraction_metadata": {
                    "quality": "needs_ocr",
                    "ocr_required": True,
                    "warnings": ["ocr_required"],
                    "extraction_reviewed": False,
                },
            },
            target_status="published",
        )

        self.assertFalse(gate["can_publish"])
        self.assertEqual(gate["blocked_reason"], "extraction_review_required")
        self.assertIn("OCR", gate["manager_message"])

    def test_training_material_extraction_review_payload_replaces_text_and_clears_ocr_warning(self):
        payload = build_training_material_extraction_review_payload(
            material={
                "id": "m1",
                "title": "Скан PDF",
                "markdown_content": "# Скан PDF\n\nТекст не извлечен автоматически.",
                "internal_notes": "Исходный файл: scan.pdf.",
                "extraction_metadata": {"quality": "needs_ocr", "ocr_required": True, "warnings": ["ocr_required"]},
            },
            reviewed_markdown="# Скан PDF\n\nРучной OCR-текст урока про первый контакт и фразу продавца.",
            reviewed_by_user_id="manager-1",
            note="OCR проверен вручную",
        )

        self.assertEqual(payload["markdown_content"], "# Скан PDF\n\nРучной OCR-текст урока про первый контакт и фразу продавца.")
        self.assertEqual(payload["extraction_metadata"]["quality"], "reviewed")
        self.assertFalse(payload["extraction_metadata"]["ocr_required"])
        self.assertTrue(payload["extraction_metadata"]["extraction_reviewed"])
        self.assertIn("manager-1", payload["internal_notes"])

    def test_training_material_learning_pack_payload_blocks_low_quality_extraction(self):
        pack = build_training_material_learning_pack_payload(
            material={
                "id": "m1",
                "title": "Скан PDF",
                "topic": "Сервис",
                "markdown_content": "# Скан PDF\n\nТекст не извлечен автоматически.",
                "extraction_metadata": {"quality": "needs_ocr", "ocr_required": True, "warnings": ["ocr_required"]},
            },
            target_slide_count=4,
        )

        self.assertEqual(pack["status"], "blocked_extraction_review_required")
        self.assertTrue(pack["review_required"])
        self.assertEqual(pack["slides"], [])

    def test_training_material_detail_payload_includes_history_and_preview(self):
        payload = build_training_material_detail_payload(
            {"id": "m1", "title": "Первый контакт", "topic": "Сервис", "category": "База", "status": "review", "markdown_content": "# Первый контакт\n\nGLAME-фраза", "tags": ["сервис"], "internal_notes": "Проверить тон"},
            history=[
                {"id": "h1", "from_status": "draft", "to_status": "review", "note": "Отправлено на проверку", "changed_by_user_id": "u1", "created_at": "2026-06-01T09:00:00Z"}
            ],
        )

        self.assertEqual(payload["material"]["title"], "Первый контакт")
        self.assertIn("<h1", payload["preview_html"])
        self.assertEqual(payload["history"][0]["to_status"], "review")
        self.assertEqual(payload["history_summary"]["events"], 1)
        self.assertIn("internal_notes", payload["material"])

    def test_training_material_status_change_payload_normalizes_and_audits_transition(self):
        payload = build_training_material_status_change_payload(
            material={"id": "m1", "status": "review"},
            new_status="published",
            changed_by_user_id="manager-1",
            note="Проверено руководителем",
        )

        self.assertEqual(payload["from_status"], "review")
        self.assertEqual(payload["to_status"], "published")
        self.assertEqual(payload["changed_by_user_id"], "manager-1")
        self.assertEqual(payload["note"], "Проверено руководителем")
        self.assertTrue(payload["requires_seller_visibility_check"])

    def test_training_material_slides_payload_orders_and_hides_internal_notes_for_seller(self):
        payload = build_training_material_slides_payload(
            [
                {"id": "slide-2", "material_id": "m1", "title": "Практика", "body": "Соберите фразу", "image_url": "https://example.com/2.jpg", "image_prompt": "internal prompt", "speaker_note": "manager only", "quiz_question": "Что сказать клиенту?", "order_index": 20, "status": "published"},
                {"id": "slide-1", "material_id": "m1", "title": "Идея", "body": "Первый контакт", "order_index": 10, "status": "published"},
                {"id": "slide-3", "material_id": "m1", "title": "Черновик", "body": "draft", "order_index": 30, "status": "draft"},
            ],
            seller_safe=True,
        )

        self.assertEqual(payload["summary"]["slides"], 2)
        self.assertEqual(payload["slides"][0]["title"], "Идея")
        self.assertEqual(payload["slides"][1]["quiz_question"], "Что сказать клиенту?")
        self.assertNotIn("speaker_note", payload["slides"][1])
        self.assertNotIn("internal prompt", str(payload))
        self.assertNotIn("Черновик", str(payload))

    def test_training_material_slide_payload_includes_admin_generation_fields(self):
        payload = build_training_material_slide_payload(
            {"id": "slide-1", "material_id": "m1", "title": "Визуальный пример", "body": "Покажите эффект на образ", "image_url": "https://example.com/look.jpg", "image_prompt": "GLAME look", "speaker_note": "Пояснить мягко", "quiz_question": "Какой эффект?", "order_index": 5, "status": "draft"},
            include_internal=True,
        )

        self.assertEqual(payload["content_format"], "learning_slide")
        self.assertEqual(payload["image_prompt"], "GLAME look")
        self.assertEqual(payload["speaker_note"], "Пояснить мягко")
        self.assertEqual(payload["status"], "draft")

    def test_training_material_slide_progress_payload_marks_viewed_slide(self):
        payload = build_training_material_slide_progress_payload(
            {"id": "progress-1", "material_id": "m1", "slide_id": "slide-1", "seller_user_id": "seller-1", "viewed_at": "2026-06-01T10:00:00Z", "completed_at": "2026-06-01T10:01:00Z"}
        )

        self.assertEqual(payload["slide_id"], "slide-1")
        self.assertTrue(payload["viewed"])
        self.assertTrue(payload["completed"])
        self.assertNotIn("seller_user_id", payload)

    def test_training_material_slides_progress_payload_counts_completed_published_slides(self):
        payload = build_training_material_slides_progress_payload(
            slides=[
                {"id": "slide-1", "material_id": "m1", "title": "Идея", "order_index": 1, "status": "published"},
                {"id": "slide-2", "material_id": "m1", "title": "Практика", "order_index": 2, "status": "published"},
                {"id": "slide-3", "material_id": "m1", "title": "Черновик", "order_index": 3, "status": "draft"},
            ],
            progress_records=[
                {"id": "p1", "material_id": "m1", "slide_id": "slide-1", "seller_user_id": "seller-1", "viewed_at": "2026-06-01T10:00:00Z", "completed_at": "2026-06-01T10:01:00Z"}
            ],
            seller_safe=True,
        )

        self.assertEqual(payload["summary"]["slides"], 2)
        self.assertEqual(payload["summary"]["completed_slides"], 1)
        self.assertEqual(payload["summary"]["progress_percent"], 50)
        self.assertFalse(payload["summary"]["material_completed"])
        self.assertTrue(payload["slides"][0]["progress"]["completed"])
        self.assertFalse(payload["slides"][1]["progress"]["completed"])
        self.assertNotIn("Черновик", str(payload))

    def test_training_material_learning_pack_payload_reformats_markdown_to_reviewable_draft(self):
        pack = build_training_material_learning_pack_payload(
            material={
                "id": "m1",
                "title": "Первый контакт",
                "topic": "Сервис",
                "category": "База стажера",
                "markdown_content": "# Первый контакт\n\nЦель: начать диалог без давления.\n\n## Регламент\n- Поприветствовать клиента.\n- Уточнить повод.\n\n## Фраза\nМожно сказать: подберем украшение под настроение образа.",
                "tags": ["сервис"],
                "competencies": ["service_contact"],
            },
            target_slide_count=4,
        )

        self.assertEqual(pack["status"], "draft_review_required")
        self.assertEqual(pack["material"]["title"], "Первый контакт")
        self.assertEqual(pack["slides"][0]["status"], "draft")
        self.assertEqual(pack["slides"][0]["content_format"], "learning_slide")
        self.assertIn("GLAME", pack["slides"][0]["image_prompt"])
        self.assertIn("руководитель", pack["slides"][0]["speaker_note"].lower())
        self.assertEqual(len(pack["slides"]), 4)
        self.assertIn("конкрет", pack["practice"]["task"].lower())
        self.assertIn("понимание", " ".join(pack["assessment"]["criteria"]).lower())
        self.assertTrue(pack["review_required"])
        self.assertNotIn("published", [slide["status"] for slide in pack["slides"]])

    def test_step_material_link_payload_marks_primary_lesson_required(self):
        payload = build_step_material_link_payload(
            {"id": "link-1", "program_id": "p1", "module_id": "mod1", "step_id": "s1", "material_id": "m1", "role": "primary_lesson", "required_to_complete": True, "order_index": 10},
            material={"id": "m1", "title": "Первый контакт", "topic": "Сервис", "status": "published", "markdown_content": "# Урок"},
        )

        self.assertEqual(payload["step_id"], "s1")
        self.assertEqual(payload["role"], "primary_lesson")
        self.assertTrue(payload["required_to_complete"])
        self.assertEqual(payload["material"]["title"], "Первый контакт")

    def test_unlocked_step_materials_opens_single_or_first_available_lesson_and_respects_locked_sequence(self):
        steps = [
            {"id": "step-1", "title": "Первый урок", "order_index": 1},
            {"id": "step-2", "title": "Второй последовательный урок", "order_index": 2},
        ]
        materials = [
            {"id": "material-1", "title": "Открытый урок", "status": "published", "order_index": 1},
            {"id": "material-2", "title": "Закрытый последовательный урок", "status": "published", "order_index": 2},
        ]
        links = [
            {"id": "link-1", "step_id": "step-1", "material_id": "material-1", "role": "primary_lesson", "required_to_complete": True, "order_index": 1},
            {"id": "link-2", "step_id": "step-2", "material_id": "material-2", "role": "primary_lesson", "required_to_complete": True, "order_index": 2},
        ]

        payload = build_unlocked_step_materials_payload(
            steps=steps,
            step_material_links=links,
            materials=materials,
            step_progress={"step-2": {"status": "locked"}},
        )

        self.assertEqual(payload["current_step"]["id"], "step-1")
        self.assertEqual(payload["current_step"]["materials"][0]["material_id"], "material-1")
        locked_step = next(item for item in payload["steps"] if item["id"] == "step-2")
        self.assertFalse(locked_step["is_unlocked"])
        self.assertEqual(locked_step["materials"], [])

    def test_step_material_practice_gate_blocks_until_required_slides_completed(self):
        gate = build_step_material_practice_gate_payload(
            step_materials=[
                {"material_id": "m1", "title": "Контакт", "required_to_complete": True, "role": "primary_lesson"},
                {"material_id": "m2", "title": "Справка", "required_to_complete": False, "role": "reference"},
            ],
            material_progress={
                "m1": {"slides": 3, "completed_slides": 2, "progress_percent": 67, "material_completed": False},
                "m2": {"slides": 1, "completed_slides": 0, "progress_percent": 0, "material_completed": False},
            },
        )

        self.assertFalse(gate["can_start_practice"])
        self.assertEqual(gate["required_materials"], 1)
        self.assertEqual(gate["completed_required_materials"], 0)
        self.assertEqual(gate["blocked_reason"], "complete_required_material_slides")
        self.assertEqual(gate["blocked_materials"][0]["material_id"], "m1")

    def test_step_material_practice_gate_opens_after_required_slides_completed(self):
        gate = build_step_material_practice_gate_payload(
            step_materials=[{"material_id": "m1", "title": "Контакт", "required_to_complete": True, "role": "primary_lesson"}],
            material_progress={"m1": {"slides": 2, "completed_slides": 2, "progress_percent": 100, "material_completed": True}},
        )

        self.assertTrue(gate["can_start_practice"])
        self.assertIsNone(gate["blocked_reason"])
        self.assertEqual(gate["completed_required_materials"], 1)

    def test_training_material_progress_analytics_payload_flags_bottlenecks(self):
        payload = build_training_material_progress_analytics_payload(
            materials=[
                {"id": "m1", "title": "Контакт", "topic": "Сервис", "status": "published", "program_code": "stylist_academy"},
                {"id": "m2", "title": "Потребность", "topic": "Сервис", "status": "published", "program_code": "stylist_academy"},
                {"id": "m3", "title": "Черновик", "topic": "Сервис", "status": "draft", "program_code": "trainee_base"},
            ],
            slides=[
                {"id": "s1", "material_id": "m1", "title": "Контакт 1", "status": "published"},
                {"id": "s2", "material_id": "m1", "title": "Контакт 2", "status": "published"},
                {"id": "s3", "material_id": "m2", "title": "Потребность 1", "status": "published"},
                {"id": "s4", "material_id": "m3", "title": "Черновик", "status": "published"},
            ],
            progress_records=[
                {"material_id": "m1", "slide_id": "s1", "seller_user_id": "u1", "completed_at": "2026-06-01T09:00:00Z"},
                {"material_id": "m1", "slide_id": "s2", "seller_user_id": "u1", "completed_at": "2026-06-01T09:05:00Z"},
                {"material_id": "m2", "slide_id": "s3", "seller_user_id": "u1", "completed_at": "2026-06-01T09:10:00Z"},
                {"material_id": "m1", "slide_id": "s1", "seller_user_id": "u2", "completed_at": "2026-06-01T10:00:00Z"},
            ],
            sellers=[{"id": "u1", "full_name": "Анна"}, {"id": "u2", "full_name": "Мария"}],
            step_material_links=[
                {"material_id": "m1", "step_id": "step-1", "required_to_complete": True},
                {"material_id": "m2", "step_id": "step-2", "required_to_complete": True},
            ],
            programs=[
                {"id": "p1", "code": "stylist_academy", "title": "Программа стилиста GLAME", "status": "active"},
                {"id": "p2", "code": "trainee_base", "title": "База стажера GLAME", "status": "active"},
            ],
            enrollments=[
                {"program_id": "p1", "seller_user_id": "u1", "status": "in_progress", "average_score": 8},
                {"program_id": "p1", "seller_user_id": "u2", "status": "completed", "completed_at": "2026-06-02T10:00:00Z", "average_score": 10},
                {"program_id": "p2", "seller_user_id": "u3", "status": "available"},
                {"program_id": "p2", "seller_user_id": "u4", "status": "archived"},
            ],
            step_submissions=[
                {"program_id": "p1", "seller_user_id": "u1", "review_status": "approved", "ai_score": 7},
                {"program_id": "p1", "seller_user_id": "u2", "review_status": "approved", "ai_score": 9},
            ],
        )

        self.assertEqual(payload["summary"]["published_materials"], 2)
        self.assertEqual(payload["summary"]["active_learners"], 2)
        self.assertEqual(payload["summary"]["completed_material_instances"], 2)
        self.assertEqual(payload["summary"]["blocked_materials"], 1)
        self.assertEqual(payload["summary"]["program_subscribed_sellers"], 3)
        self.assertEqual(payload["summary"]["program_in_progress_sellers"], 2)
        self.assertEqual(payload["summary"]["program_completed_sellers"], 1)
        self.assertEqual(payload["summary"]["average_understanding_percent"], 85)
        self.assertEqual(payload["programs"][0]["title"], "Программа стилиста GLAME")
        self.assertEqual(payload["programs"][0]["subscribed_sellers"], 2)
        self.assertEqual(payload["programs"][0]["in_progress_sellers"], 1)
        self.assertEqual(payload["programs"][0]["completed_sellers"], 1)
        self.assertEqual(payload["programs"][0]["average_understanding_percent"], 85)
        self.assertEqual(payload["materials"][0]["title"], "Потребность")
        self.assertEqual(payload["materials"][0]["completion_percent"], 50)
        self.assertEqual(payload["materials"][0]["risk_level"], "high")
        self.assertIn("Потребность", payload["recommendations"][0]["text"])
        self.assertNotIn("Черновик", str(payload))

    def test_training_material_publish_cascade_publishes_slides_and_visual_assets(self):
        payload = build_training_material_publish_cascade_payload(
            material={"id": "m1", "status": "published"},
            slides=[
                {"id": "s1", "status": "draft", "image_url": "data:image/png;base64,AAA"},
                {"id": "s2", "status": "review", "image_url": "https://cdn.example/slide-2.jpg"},
                {"id": "s3", "status": "published", "image_url": None},
            ],
            extraction_metadata={
                "visual_assets": [
                    {"asset_id": "a1", "status": "pending_review", "image_url": "data:image/png;base64,AAA", "attached_slide_id": "s1"},
                    {"asset_id": "a2", "status": "approved", "image_url": "https://cdn.example/slide-2.jpg"},
                    {"asset_id": "a3", "status": "rejected", "image_url": "https://cdn.example/rejected.jpg"},
                ],
            },
            reviewed_by_user_id="manager-1",
        )

        self.assertEqual(payload["slides_to_publish"], ["s1", "s2"])
        self.assertEqual(payload["published_slides_count"], 2)
        assets = payload["extraction_metadata"]["visual_assets"]
        self.assertEqual(assets[0]["status"], "attached")
        self.assertEqual(assets[1]["status"], "approved")
        self.assertEqual(assets[2]["status"], "rejected")
        self.assertEqual(payload["visual_assets_summary"]["approved"], 1)
        self.assertEqual(payload["visual_assets_summary"]["attached"], 1)

    def test_unlocked_step_materials_payload_only_exposes_current_published_materials(self):
        payload = build_unlocked_step_materials_payload(
            steps=[
                {"id": "s1", "title": "Первый контакт", "order_index": 1},
                {"id": "s2", "title": "Выявление потребности", "order_index": 2},
            ],
            step_material_links=[
                {"id": "l1", "step_id": "s1", "material_id": "m1", "role": "primary_lesson", "required_to_complete": True, "order_index": 1},
                {"id": "l2", "step_id": "s2", "material_id": "m2", "role": "primary_lesson", "required_to_complete": True, "order_index": 1},
                {"id": "l3", "step_id": "s1", "material_id": "m3", "role": "reference", "required_to_complete": False, "order_index": 2},
            ],
            materials=[
                {"id": "m1", "title": "Контакт", "topic": "Сервис", "status": "published", "markdown_content": "# Контакт"},
                {"id": "m2", "title": "Потребность", "topic": "Сервис", "status": "published", "markdown_content": "# Потребность"},
                {"id": "m3", "title": "Черновик", "topic": "Сервис", "status": "draft", "markdown_content": "# draft"},
            ],
            step_progress={"s1": {"status": "available"}, "s2": {"status": "locked"}},
        )

        self.assertEqual(payload["current_step"]["id"], "s1")
        self.assertEqual(payload["summary"]["unlocked_materials"], 1)
        self.assertEqual(payload["steps"][0]["materials"][0]["title"], "Контакт")
        self.assertEqual(payload["steps"][1]["locked_reason"], "complete_previous_step")
        self.assertNotIn("Черновик", str(payload))

    def test_seller_training_account_matching_payload_flags_unresolved_kpi_sellers(self):
        payload = build_seller_training_account_matching_payload(
            kpi_sellers=[
                {"seller_external_id": "1c-anna", "seller_name": "Анна Смирнова", "store_name": "ТРК Центрум"},
                {"seller_external_id": "1c-maria", "seller_name": "Мария Иванова", "store_name": "Меганом"},
                {"seller_external_id": "1c-no-name", "seller_name": "Без имени", "store_name": "ТРК Центрум"},
            ],
            users=[
                {"id": "user-1", "full_name": "Анна Смирнова", "email": "anna@example.com", "preferences": {"seller_external_id": "1c-anna"}},
                {"id": "user-2", "full_name": "Мария И.", "email": "maria@example.com", "preferences": {"seller_name": "Мария Иванова"}},
            ],
        )

        self.assertEqual(payload["summary"]["total_kpi_sellers"], 3)
        self.assertEqual(payload["summary"]["matched_by_external_id"], 1)
        self.assertEqual(payload["summary"]["matched_by_name"], 1)
        self.assertEqual(payload["summary"]["unresolved"], 1)
        self.assertEqual(payload["matches"][0]["match_type"], "external_id")
        self.assertEqual(payload["matches"][1]["match_type"], "name_fallback")
        self.assertEqual(payload["unresolved"][0]["seller_external_id"], "1c-no-name")
        self.assertTrue(payload["recommendations"])

    def test_personal_training_kpi_summary_payload_builds_next_action_for_seller_card(self):
        payload = build_personal_training_kpi_summary_payload(
            seller={"full_name": "Анна Смирнова", "email": "anna@example.com"},
            training_profile={
                "level": "Стажер",
                "completed_steps": 2,
                "total_steps": 8,
                "attestation_ready": False,
                "achievements": [{"code": "first_step", "title": "Первый шаг"}],
                "weakest_competencies": [{"code": "service_contact", "label": "Первый контакт", "percent": 25}],
            },
            program_cards=[
                {"program": {"title": "Программа стажера GLAME"}, "progress": {"completed_steps": 2, "total_steps": 8}, "next_action": {"label": "Продолжить этап", "target_id": "step-2"}},
            ],
            kpi={"completion_percent": 62, "avg_check": 4200, "items_per_check": 1.1},
        )

        self.assertEqual(payload["level"], "Стажер")
        self.assertEqual(payload["progress_percent"], 25)
        self.assertEqual(payload["priority"], "high")
        self.assertEqual(payload["next_program_title"], "Программа стажера GLAME")
        self.assertIn("Первый контакт", payload["recommended_training_focus"])
        self.assertIn("средний чек", payload["kpi_focus"])
        self.assertTrue(payload["manager_recommendation"])


if __name__ == "__main__":
    unittest.main()
