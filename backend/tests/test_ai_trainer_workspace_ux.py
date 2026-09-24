import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "components" / "training" / "ConsultantTrainingAdminPage.tsx"


class AiTrainerWorkspaceUxTests(unittest.TestCase):
    def test_primary_work_is_split_into_four_workspaces(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Программа стажёра", source)
        self.assertIn("Исходники и AI", source)
        self.assertIn("Назначения", source)
        self.assertIn("Результаты и экзамены", source)
        self.assertIn("ШАГ {number}", source)
        self.assertIn("['4', 'Назначение'", source)

    def test_program_workspace_starts_with_trainee_program(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("program.code === 'trainee_base'", source)
        self.assertIn("Рабочий контур", source)

    def test_program_step_opens_its_slide_editor_with_learner_preview(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("openStepSlideEditor", source)
        self.assertIn("/step-materials", source)
        self.assertIn("Предпросмотр для стажёра", source)
        self.assertIn("Эта карточка повторяет подачу слайда", source)

    def test_document_import_shows_an_honest_in_progress_status(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("importElapsedSeconds", source)
        self.assertIn("role=\"progressbar\"", source)
        self.assertIn("Не закрывайте страницу", source)

    def test_material_editor_groups_sources_and_offers_learner_preview_popup(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("1. Исходные материалы и картинки", source)
        self.assertIn("2. Подготовка слайдов", source)
        self.assertIn("3. Пройти как стажёр", source)
        self.assertIn("Режим симуляции · как у стажёра", source)

    def test_slide_visuals_are_requested_from_contentmaker_not_pdf_pages(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Сгенерировать визуал AI", source)
        self.assertIn("PDF‑скриншоты сюда не попадают", source)
        self.assertIn("Ранее сгенерированные визуалы", source)

    def test_slide_editor_supports_upload_and_platform_media_library(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("Выбрать из медиатеки", source)
        self.assertIn("Загрузить фото", source)
        self.assertIn("Медиатека платформы", source)
        self.assertIn("/media-library", source)

    def test_slide_cards_open_a_full_learner_course_simulation(self):
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("openLearnerCoursePreview", source)
        self.assertIn("Следующий слайд", source)
        self.assertIn("Перейти к опроснику", source)
        self.assertIn("Полный цикл пройден", source)


if __name__ == "__main__":
    unittest.main()
