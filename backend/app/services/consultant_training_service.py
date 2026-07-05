from __future__ import annotations

import asyncio
import base64
import importlib.util
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import re
from pathlib import PurePosixPath
import zipfile
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

ALLOWED_TOPIC_STATUSES = {
    "draft",
    "monthly_approval",
    "approved",
    "needs_revision",
    "ready_to_publish",
    "sent_to_consultants",
    "completion_tracking",
    "archived",
}

REVISION_THRESHOLD = 4
ACCEPT_THRESHOLD = 8

ALLOWED_PROGRAM_STATUSES = {
    "locked",
    "available",
    "access_requested",
    "in_progress",
    "waiting_review",
    "needs_revision",
    "completed",
    "certified",
    "archived",
}

ALLOWED_STEP_SUBMISSION_STATUSES = {
    "review_pending",
    "revision_draft",
    "approved",
    "revision_requested",
    "accepted",
    "sent_to_consultant",
}

ALLOWED_ATTESTATION_STATUSES = {
    "draft",
    "submitted",
    "review_pending",
    "revision_requested",
    "passed",
    "failed",
    "certified",
}

ALLOWED_MENTOR_MESSAGE_ROLES = {"user", "mentor"}

ALLOWED_SHIFT_REFLECTION_STATUSES = {"submitted", "completed", "needs_coaching", "reviewed"}
ALLOWED_COACHING_ACTION_STATUSES = {"new", "planned", "discussed", "resolved", "cancelled"}
ALLOWED_TRAINING_MATERIAL_STATUSES = {"draft", "review", "published", "archived"}

TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE = "training-material-reformatter-agent"
DEFAULT_TRAINING_MATERIAL_REFORMATTER_PROMPT = """Ты — AI-агент GLAME для переформатирования загруженных исходников обучения продавцов в учебный learning pack.

Твоя задача: из исходного документа/Markdown сделать черновой учебный пакет для продавца GLAME: слайды, практику, шаблон ответа, критерии проверки и пул проверочных вопросов для оценки знания.

Правила GLAME:
- не публикуй материал напрямую продавцам; результат всегда draft/review_required;
- сохраняй смысл исходника, но переписывай его как обучение консультанта-стилиста, а не как сухой документ;
- делай контент конкретным: клиентская ситуация, украшение, эффект на образ, GLAME-фраза, действие в смене;
- тон поддерживающий, премиальный, без давления на клиента и без оценок внешности;
- запрещены агрессивные продажи: “берите”, “дожимайте”, “закрывайте клиента”, “всем подходит”, “must-have”;
- image_prompt и speaker_note — только для администратора/руководителя, не для продавца;
- финальную обратную связь и публикацию подтверждает руководитель;
- question_pool должен содержать 8–12 проверочных вопросов разного типа: короткий ответ, сценарий клиента, выбор формулировки, do/don't, применение в смене. Каждый вопрос должен иметь ожидаемый ответ/критерии и уровень сложности.

Форматируй ответ строго как JSON по запрошенной схеме. Слайды и вопросы должны быть самостоятельными, понятными продавцу и готовыми к проверке руководителем."""

COMPETENCY_LABELS = {
    "service_contact": "Первый контакт и сервис",
    "glame_language": "Язык GLAME",
    "product_knowledge": "Продукт и материалы",
    "styling_effect": "Эффект украшения на образ",
    "sales_without_pressure": "Продажи без давления",
    "operations": "Операционные стандарты",
    "brand_standard": "Стандарты бренда",
}

DEFAULT_TRAINING_PROGRAMS = [
    {
        "code": "trainee_base",
        "title": "Программа стажера GLAME",
        "description": "Базовая программа адаптации: бренд, сервис, продукт, продажи и операционные стандарты до самостоятельной смены.",
        "program_type": "trainee_base",
        "status": "active",
        "is_required": True,
        "order_index": 10,
        "meta": {"accent": "warm", "target_level": "Junior Consultant"},
    },
    {
        "code": "stylist_academy",
        "title": "Программа стилиста GLAME",
        "description": "Постоянное развитие консультанта-стилиста: эффект украшений на образ, 4 DNA, сценарии клиента, комплекты и язык GLAME.",
        "program_type": "stylist_academy",
        "status": "active",
        "is_required": True,
        "order_index": 20,
        "meta": {"accent": "slate", "target_level": "Stylist Consultant"},
    },
]

DEFAULT_TRAINING_STRUCTURE = {
    "trainee_base": [
        {
            "title": "Бренд и стандарты GLAME",
            "description": "Миссия, роль консультанта, внешний вид и базовая культура сервиса.",
            "order_index": 10,
            "steps": [
                {"title": "Миссия и ценности GLAME", "order_index": 10, "competencies": ["brand_standard", "service_contact"]},
                {"title": "Первый контакт 30–60 секунд", "order_index": 20, "competencies": ["service_contact", "glame_language"]},
            ],
        },
        {
            "title": "Продукт и операции",
            "description": "Ассортимент, материалы, уход, касса и правила смены.",
            "order_index": 20,
            "steps": [
                {"title": "Материалы и уход за украшениями", "order_index": 10, "competencies": ["product_knowledge"]},
                {"title": "Касса, сертификаты и возвраты", "order_index": 20, "competencies": ["operations"]},
            ],
        },
    ],
    "stylist_academy": [
        {
            "title": "Украшение как часть образа",
            "description": "Как объяснять клиенту эффект украшения на образ без давления.",
            "order_index": 10,
            "steps": [
                {"title": "Эффект украшения на образ", "order_index": 10, "competencies": ["styling_effect", "glame_language"]},
                {"title": "Комплектность без давления", "order_index": 20, "competencies": ["sales_bundle", "glame_language"]},
            ],
        },
        {
            "title": "4 DNA GLAME",
            "description": "Classic, Romantic, Dramatic, Natural как база стилистического подбора.",
            "order_index": 20,
            "steps": [
                {"title": "Classic и Romantic DNA", "order_index": 10, "competencies": ["style_dna"]},
                {"title": "Dramatic и Natural DNA", "order_index": 20, "competencies": ["style_dna"]},
            ],
        },
    ],
}

POSITIVE_EFFECT_TERMS = [
    "образ",
    "собран",
    "цельн",
    "акцент",
    "характер",
    "мягк",
    "не перегруж",
    "вечерн",
    "универсаль",
    "рубаш",
    "плать",
    "жакет",
    "носить",
    "следующим шагом",
]

WEAK_OR_FORBIDDEN_TERMS = [
    "берите",
    "дожм",
    "закрой",
    "продайте",
    "модно",
    "must-have",
    "всем подходит",
    "вам идёт",
    "круглое лицо",
]

_SCHEMA_LOCK = asyncio.Lock()
_SCHEMA_READY = False
_SCHEMA_ADVISORY_LOCK_ID = 4931802401


async def ensure_consultant_training_schema(db) -> None:
    """Create the trainer tables when migrations have not been applied yet.

    The project has several deployment modes; this keeps the MVP usable on the
    running development platform while the Alembic migration remains the durable
    schema path.
    """
    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    from sqlalchemy import text

    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _SCHEMA_ADVISORY_LOCK_ID})

        statements = [
            """
            CREATE TABLE IF NOT EXISTS consultant_training_programs (
                id UUID PRIMARY KEY,
                code VARCHAR(80) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                program_type VARCHAR(80) NOT NULL DEFAULT 'custom',
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                audience_rules JSON NOT NULL DEFAULT '{}'::json,
                is_required BOOLEAN NOT NULL DEFAULT true,
                order_index INTEGER NOT NULL DEFAULT 100,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_programs_code ON consultant_training_programs(code)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_programs_type_status ON consultant_training_programs(program_type, status)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_modules (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                order_index INTEGER NOT NULL DEFAULT 100,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_modules_program_id ON consultant_training_modules(program_id)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_steps (
                id UUID PRIMARY KEY,
                module_id UUID NOT NULL REFERENCES consultant_training_modules(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                lesson_text TEXT,
                practice_text TEXT,
                answer_template TEXT,
                assessment_rubric JSON NOT NULL DEFAULT '{}'::json,
                competencies JSON NOT NULL DEFAULT '[]'::json,
                unlock_rule JSON NOT NULL DEFAULT '{}'::json,
                is_required BOOLEAN NOT NULL DEFAULT true,
                order_index INTEGER NOT NULL DEFAULT 100,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_steps_module_id ON consultant_training_steps(module_id)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_topics (
                id UUID PRIMARY KEY,
                lesson_date DATE NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                theme VARCHAR(500),
                goal TEXT,
                material_text TEXT,
                assignment_text TEXT,
                focus_text TEXT,
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                approval_comment TEXT,
                approved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                approved_at TIMESTAMPTZ,
                published_at TIMESTAMPTZ,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS consultant_training_assignments (
                id UUID PRIMARY KEY,
                topic_id UUID NOT NULL REFERENCES consultant_training_topics(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(50) NOT NULL DEFAULT 'not_opened',
                opened_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ,
                CONSTRAINT uq_consultant_training_assignment_topic_seller UNIQUE (topic_id, seller_user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS consultant_training_submissions (
                id UUID PRIMARY KEY,
                topic_id UUID NOT NULL REFERENCES consultant_training_topics(id) ON DELETE CASCADE,
                assignment_id UUID REFERENCES consultant_training_assignments(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                practice_answer TEXT NOT NULL,
                evening_review TEXT,
                ai_score INTEGER,
                ai_evaluation JSON NOT NULL DEFAULT '{}'::json,
                review_status VARCHAR(50) NOT NULL DEFAULT 'review_pending',
                manager_feedback TEXT,
                consultant_feedback TEXT,
                reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMPTZ,
                sent_to_consultant_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_topics_status_date ON consultant_training_topics(status, lesson_date)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_enrollments (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(50) NOT NULL DEFAULT 'available',
                current_topic_id UUID REFERENCES consultant_training_topics(id) ON DELETE SET NULL,
                average_score INTEGER,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ,
                CONSTRAINT uq_consultant_training_enrollment_program_seller UNIQUE (program_id, seller_user_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_enrollments_program_id ON consultant_training_enrollments(program_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_enrollments_seller_user_id ON consultant_training_enrollments(seller_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_enrollments_status ON consultant_training_enrollments(status)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_attestations (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                enrollment_id UUID REFERENCES consultant_training_enrollments(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                attestation_type VARCHAR(80) NOT NULL DEFAULT 'trainee_final',
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                task_payload JSON NOT NULL DEFAULT '{}'::json,
                answer_payload JSON NOT NULL DEFAULT '{}'::json,
                competency_snapshot JSON NOT NULL DEFAULT '{}'::json,
                ai_score INTEGER,
                ai_evaluation JSON NOT NULL DEFAULT '{}'::json,
                manager_decision VARCHAR(50),
                manager_feedback TEXT,
                certified_level VARCHAR(80),
                reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                submitted_at TIMESTAMPTZ,
                reviewed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_attestations_program_id ON consultant_training_attestations(program_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_attestations_seller_user_id ON consultant_training_attestations(seller_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_attestations_review ON consultant_training_attestations(status, created_at)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_mentor_messages (
                id UUID PRIMARY KEY,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                program_id UUID REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                step_id UUID REFERENCES consultant_training_steps(id) ON DELETE SET NULL,
                sender_role VARCHAR(20) NOT NULL DEFAULT 'mentor',
                question_text TEXT,
                response_text TEXT NOT NULL,
                context JSON NOT NULL DEFAULT '{}'::json,
                risk_flags JSON NOT NULL DEFAULT '[]'::json,
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_mentor_messages_seller_created ON consultant_training_mentor_messages(seller_user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_mentor_messages_program_id ON consultant_training_mentor_messages(program_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_mentor_messages_step_id ON consultant_training_mentor_messages(step_id)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_shift_reflections (
                id UUID PRIMARY KEY,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                shift_date DATE,
                store_name VARCHAR(255),
                daily_focus_snapshot JSON NOT NULL DEFAULT '{}'::json,
                reflection_payload JSON NOT NULL DEFAULT '{}'::json,
                ai_score INTEGER,
                ai_evaluation JSON NOT NULL DEFAULT '{}'::json,
                status VARCHAR(50) NOT NULL DEFAULT 'submitted',
                risk_flags JSON NOT NULL DEFAULT '[]'::json,
                manager_note TEXT,
                manager_feedback TEXT,
                reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_shift_reflections_seller_date ON consultant_training_shift_reflections(seller_user_id, shift_date)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_shift_reflections_status_created ON consultant_training_shift_reflections(status, created_at)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_coaching_actions (
                id UUID PRIMARY KEY,
                reflection_id UUID REFERENCES consultant_training_shift_reflections(id) ON DELETE SET NULL,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'new',
                planned_for DATE,
                store_name VARCHAR(255),
                coaching_topic TEXT NOT NULL,
                competency VARCHAR(255),
                kpi_metric VARCHAR(255),
                risk_flags JSON NOT NULL DEFAULT '[]'::json,
                manager_script TEXT,
                seller_next_step TEXT,
                manager_result TEXT,
                seller_visible_feedback TEXT,
                discussed_at TIMESTAMPTZ,
                resolved_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_coaching_actions_seller_status ON consultant_training_coaching_actions(seller_user_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_coaching_actions_status_planned ON consultant_training_coaching_actions(status, planned_for)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_materials (
                id UUID PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                topic VARCHAR(255) NOT NULL DEFAULT 'Общее',
                category VARCHAR(255) NOT NULL DEFAULT 'Библиотека GLAME',
                description TEXT,
                markdown_content TEXT NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                tags JSON NOT NULL DEFAULT '[]'::json,
                source_type VARCHAR(80) NOT NULL DEFAULT 'manual_md',
                extraction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                program_code VARCHAR(80),
                competencies JSON NOT NULL DEFAULT '[]'::json,
                internal_notes TEXT,
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                approved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                approved_at TIMESTAMPTZ,
                order_index INTEGER NOT NULL DEFAULT 100,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_materials_topic_status ON consultant_training_materials(topic, status)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_materials_category_order ON consultant_training_materials(category, order_index)",
            "ALTER TABLE consultant_training_materials ADD COLUMN IF NOT EXISTS extraction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_materials_extraction_metadata ON consultant_training_materials USING GIN (extraction_metadata)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_materials_program_code ON consultant_training_materials(program_code)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_material_slides (
                id UUID PRIMARY KEY,
                material_id UUID NOT NULL REFERENCES consultant_training_materials(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                body TEXT,
                image_url TEXT,
                image_prompt TEXT,
                speaker_note TEXT,
                quiz_question TEXT,
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                order_index INTEGER NOT NULL DEFAULT 100,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_material_slides_material_order ON consultant_training_material_slides(material_id, order_index)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_material_slides_status ON consultant_training_material_slides(status)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_material_slide_progress (
                id UUID PRIMARY KEY,
                material_id UUID NOT NULL REFERENCES consultant_training_materials(id) ON DELETE CASCADE,
                slide_id UUID NOT NULL REFERENCES consultant_training_material_slides(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                viewed_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ,
                CONSTRAINT uq_consultant_training_slide_progress_seller UNIQUE (slide_id, seller_user_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_slide_progress_material_seller ON consultant_training_material_slide_progress(material_id, seller_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_slide_progress_slide_seller ON consultant_training_material_slide_progress(slide_id, seller_user_id)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_step_materials (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                module_id UUID REFERENCES consultant_training_modules(id) ON DELETE CASCADE,
                step_id UUID NOT NULL REFERENCES consultant_training_steps(id) ON DELETE CASCADE,
                material_id UUID NOT NULL REFERENCES consultant_training_materials(id) ON DELETE CASCADE,
                role VARCHAR(80) NOT NULL DEFAULT 'primary_lesson',
                required_to_complete BOOLEAN NOT NULL DEFAULT true,
                order_index INTEGER NOT NULL DEFAULT 100,
                meta JSON NOT NULL DEFAULT '{}'::json,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ,
                CONSTRAINT uq_consultant_training_step_material_role UNIQUE (step_id, material_id, role)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_materials_step_order ON consultant_training_step_materials(step_id, order_index)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_materials_program ON consultant_training_step_materials(program_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_materials_material ON consultant_training_step_materials(material_id)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_material_status_history (
                id UUID PRIMARY KEY,
                material_id UUID NOT NULL REFERENCES consultant_training_materials(id) ON DELETE CASCADE,
                from_status VARCHAR(50),
                to_status VARCHAR(50) NOT NULL,
                note TEXT,
                changed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_material_status_history_material_created ON consultant_training_material_status_history(material_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_material_status_history_to_status ON consultant_training_material_status_history(to_status)",
            """
            CREATE TABLE IF NOT EXISTS consultant_training_step_submissions (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES consultant_training_programs(id) ON DELETE CASCADE,
                step_id UUID NOT NULL REFERENCES consultant_training_steps(id) ON DELETE CASCADE,
                enrollment_id UUID REFERENCES consultant_training_enrollments(id) ON DELETE CASCADE,
                seller_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                practice_answer TEXT NOT NULL,
                evening_review TEXT,
                ai_score INTEGER,
                ai_evaluation JSON NOT NULL DEFAULT '{}'::json,
                review_status VARCHAR(50) NOT NULL DEFAULT 'review_pending',
                manager_feedback TEXT,
                consultant_feedback TEXT,
                reviewed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMPTZ,
                sent_to_consultant_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_submissions_program_id ON consultant_training_step_submissions(program_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_submissions_step_id ON consultant_training_step_submissions(step_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_submissions_seller_user_id ON consultant_training_step_submissions(seller_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_step_submissions_review ON consultant_training_step_submissions(review_status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_assignments_seller_user_id ON consultant_training_assignments(seller_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_assignments_topic_id ON consultant_training_assignments(topic_id)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_submissions_review ON consultant_training_submissions(review_status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_consultant_training_submissions_seller_user_id ON consultant_training_submissions(seller_user_id)",
        ]
        for statement in statements:
            await db.execute(text(statement))
        for program in DEFAULT_TRAINING_PROGRAMS:
            await db.execute(
                text(
                    """
                    INSERT INTO consultant_training_programs (
                        id, code, title, description, program_type, status,
                        audience_rules, is_required, order_index, meta
                    ) VALUES (
                        :id, :code, :title, :description, :program_type, :status,
                        :audience_rules, :is_required, :order_index, :meta
                    )
                    ON CONFLICT (code) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        program_type = EXCLUDED.program_type,
                        status = EXCLUDED.status,
                        is_required = EXCLUDED.is_required,
                        order_index = EXCLUDED.order_index,
                        meta = EXCLUDED.meta,
                        updated_at = now()
                    """
                ),
                {
                    **program,
                    "id": uuid4(),
                    "audience_rules": json.dumps(program.get("audience_rules") or {}),
                    "meta": json.dumps(program.get("meta") or {}),
                },
            )
        for program in DEFAULT_TRAINING_PROGRAMS:
            program_row = (await db.execute(text("SELECT id FROM consultant_training_programs WHERE code = :code"), {"code": program["code"]})).first()
            if not program_row:
                continue
            program_id = program_row[0]
            existing_modules = (await db.execute(text("SELECT count(*) FROM consultant_training_modules WHERE program_id = :program_id"), {"program_id": program_id})).scalar() or 0
            if existing_modules:
                continue
            for module in DEFAULT_TRAINING_STRUCTURE.get(program["code"], []):
                module_id = uuid4()
                await db.execute(
                    text(
                        """
                        INSERT INTO consultant_training_modules (id, program_id, title, description, order_index, meta)
                        VALUES (:id, :program_id, :title, :description, :order_index, :meta)
                        """
                    ),
                    {
                        "id": module_id,
                        "program_id": program_id,
                        "title": module["title"],
                        "description": module.get("description"),
                        "order_index": module.get("order_index", 100),
                        "meta": json.dumps(module.get("meta") or {}),
                    },
                )
                for step in module.get("steps", []):
                    await db.execute(
                        text(
                            """
                            INSERT INTO consultant_training_steps (
                                id, module_id, title, lesson_text, practice_text, answer_template,
                                assessment_rubric, competencies, unlock_rule, is_required, order_index, meta
                            ) VALUES (
                                :id, :module_id, :title, :lesson_text, :practice_text, :answer_template,
                                :assessment_rubric, :competencies, :unlock_rule, :is_required, :order_index, :meta
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "module_id": module_id,
                            "title": step["title"],
                            "lesson_text": step.get("lesson_text"),
                            "practice_text": step.get("practice_text"),
                            "answer_template": step.get("answer_template"),
                            "assessment_rubric": json.dumps(step.get("assessment_rubric") or {}),
                            "competencies": json.dumps(step.get("competencies") or []),
                            "unlock_rule": json.dumps(step.get("unlock_rule") or {}),
                            "is_required": step.get("is_required", True),
                            "order_index": step.get("order_index", 100),
                            "meta": json.dumps(step.get("meta") or {}),
                        },
                    )
        await db.commit()
        _SCHEMA_READY = True


def normalize_topic_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    if status in ALLOWED_TOPIC_STATUSES:
        return status
    return "draft"


def normalize_program_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    if status in ALLOWED_PROGRAM_STATUSES:
        return status
    return "available"


def _dict_value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _program_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "да"}
    return bool(value)


def build_program_assignment_removal_payload(*, enrollment: Any, removed_by_user_id: str, note: str | None = None, status: str = "archived") -> dict[str, Any]:
    previous_status = normalize_program_status(_dict_value(enrollment, "status", None))
    meta = dict(_dict_value(enrollment, "meta", {}) or {})
    meta.update(
        {
            "unassigned_at": datetime.now(timezone.utc).isoformat(),
            "unassigned_by_user_id": str(removed_by_user_id),
            "unassignment_note": note,
            "previous_status_before_unassignment": previous_status,
        }
    )
    return {
        "status": normalize_program_status(status),
        "previous_status": previous_status,
        "meta": meta,
    }


def build_program_card_payload(*, program: Any, enrollment: Any = None, next_assignment: dict | None = None) -> dict[str, Any]:
    completed_steps = int(_dict_value(enrollment, "completed_steps", 0) or 0)
    total_steps = int(_dict_value(enrollment, "total_steps", 0) or 0)
    percent = round((completed_steps / total_steps) * 100) if total_steps else 0
    status = normalize_program_status(_dict_value(enrollment, "status", None))
    pending_reviews = int(_dict_value(enrollment, "pending_reviews", 0) or 0)
    revision_count = int(_dict_value(enrollment, "revision_count", 0) or 0)
    average_score = _dict_value(enrollment, "average_score", None)

    if revision_count:
        cta = "Доработать"
    elif pending_reviews:
        cta = "Ожидает проверки"
    elif status in {"completed", "certified"}:
        cta = "Посмотреть результат"
    elif status == "access_requested":
        cta = "Запрос отправлен"
    elif status in {"locked", "archived"}:
        meta = _dict_value(enrollment, "meta", {}) or {}
        cta = "Запросить допуск" if meta.get("not_assigned") else "Недоступно"
    elif next_assignment:
        cta = "Продолжить"
    else:
        meta = _dict_value(program, "meta", {}) or {}
        cta = "Подписаться" if (meta.get("open_enrollment") or meta.get("free_enrollment") or meta.get("self_enrollment")) else "Открыть программу"

    return {
        "id": str(_dict_value(program, "id")),
        "code": _dict_value(program, "code"),
        "title": _dict_value(program, "title"),
        "description": _dict_value(program, "description"),
        "program_type": _dict_value(program, "program_type"),
        "program_status": _dict_value(program, "status", "active"),
        "status": status,
        "access_mode": "free" if ((_dict_value(program, "meta", {}) or {}).get("open_enrollment") or (_dict_value(program, "meta", {}) or {}).get("free_enrollment") or (_dict_value(program, "meta", {}) or {}).get("self_enrollment")) else ("requested" if status == "access_requested" else ("assigned" if status not in {"locked", "archived"} else "request_required")),
        "is_required": _program_bool(_dict_value(program, "is_required", False)),
        "order_index": int(_dict_value(program, "order_index", 100) or 100),
        "average_score": average_score,
        "progress": {
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "percent": percent,
            "pending_reviews": pending_reviews,
            "revision_count": revision_count,
        },
        "next_assignment": next_assignment,
        "cta": cta,
        "meta": _dict_value(program, "meta", {}) or {},
    }


def normalize_training_material_status(status: str | None) -> str:
    return status if status in ALLOWED_TRAINING_MATERIAL_STATUSES else "draft"


def build_training_material_source_file_payload(extraction: dict[str, Any] | None, *, include_content: bool = False) -> dict[str, Any] | None:
    source_file = (extraction or {}).get("source_file") if isinstance(extraction, dict) else None
    if not isinstance(source_file, dict):
        filename = (extraction or {}).get("filename") if isinstance(extraction, dict) else None
        if not filename:
            return None
        source_file = {"filename": filename, "has_content": False}
    payload = {
        "filename": source_file.get("filename") or (extraction or {}).get("filename"),
        "mime_type": source_file.get("mime_type"),
        "extension": source_file.get("extension") or (extraction or {}).get("extension"),
        "size_bytes": source_file.get("size_bytes"),
        "has_content": bool(source_file.get("content_base64")) or bool(source_file.get("has_content")),
        "storage": source_file.get("storage") or "extraction_metadata",
    }
    if include_content and source_file.get("content_base64"):
        payload["content_base64"] = source_file.get("content_base64")
    return payload


def build_training_material_visual_assets_payload(extraction: dict[str, Any] | None, *, include_content: bool = False) -> list[dict[str, Any]]:
    assets = (extraction or {}).get("visual_assets") if isinstance(extraction, dict) else []
    if not isinstance(assets, list):
        return []
    payload: list[dict[str, Any]] = []
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            continue
        content_base64 = asset.get("content_base64")
        item = {
            "asset_id": str(asset.get("asset_id") or asset.get("id") or f"visual-asset-{index}"),
            "filename": asset.get("filename") or f"visual-asset-{index}.{asset.get('extension') or 'png'}",
            "mime_type": asset.get("mime_type") or "image/png",
            "extension": asset.get("extension") or str(asset.get("mime_type") or "image/png").split("/")[-1],
            "page": asset.get("page"),
            "image_index": asset.get("image_index"),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "size_bytes": asset.get("size_bytes"),
            "status": asset.get("status") or "pending_review",
            "source": asset.get("source") or "pdf_embedded_image",
            "admin_only": True,
            "has_content": bool(content_base64) or bool(asset.get("has_content")),
            "storage": asset.get("storage") or "extraction_metadata",
            "review_note": asset.get("review_note"),
            "reviewed_by_user_id": asset.get("reviewed_by_user_id"),
            "reviewed_at": asset.get("reviewed_at"),
            "attached_slide_id": asset.get("attached_slide_id"),
        }
        if include_content and content_base64:
            item["content_base64"] = content_base64
            item["data_url"] = f"data:{item['mime_type']};base64,{content_base64}"
            item["image_url"] = f"data:{item['mime_type']};base64,{content_base64}"
        payload.append(item)
    return payload


def build_training_material_visual_asset_update_payload(
    extraction: dict[str, Any] | None,
    *,
    asset_id: str,
    status: str,
    note: str | None = None,
    slide_id: str | None = None,
    reviewed_by_user_id: str | None = None,
) -> dict[str, Any]:
    allowed = {"pending_review", "approved", "rejected", "attached"}
    normalized_status = status if status in allowed else "pending_review"
    updated = dict(extraction or {})
    assets = list(updated.get("visual_assets") or [])
    matched = False
    now = datetime.now(timezone.utc).isoformat()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            continue
        if str(asset.get("asset_id") or asset.get("id") or "") == str(asset_id):
            next_asset = dict(asset)
            next_asset["status"] = normalized_status
            next_asset["review_note"] = note
            next_asset["reviewed_by_user_id"] = reviewed_by_user_id
            next_asset["reviewed_at"] = now
            if slide_id:
                next_asset["attached_slide_id"] = str(slide_id)
            assets[index] = next_asset
            matched = True
            break
    if not matched:
        raise ValueError("visual_asset_not_found")
    updated["visual_assets"] = assets
    summary = {"total": 0, "pending_review": 0, "approved": 0, "rejected": 0, "attached": 0}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        summary["total"] += 1
        asset_status = asset.get("status") or "pending_review"
        if asset_status in summary:
            summary[asset_status] += 1
    updated["visual_assets_summary"] = summary
    return updated


def extract_training_pdf_visual_assets(data: bytes, *, filename: str | None = None, max_assets: int = 24, max_inline_bytes: int = 2 * 1024 * 1024) -> list[dict[str, Any]]:
    def _asset_from_image_bytes(
        *,
        image_bytes: bytes,
        page_number: int,
        image_index: int,
        extension: str,
        mime_type: str,
        width: int | None,
        height: int | None,
        source: str,
    ) -> dict[str, Any] | None:
        if not image_bytes:
            return None
        digest = hashlib.sha256(image_bytes).hexdigest()
        if digest in seen_hashes:
            return None
        seen_hashes.add(digest)
        safe_asset_id = f"pdf-image-{digest[:12]}"
        asset: dict[str, Any] = {
            "asset_id": safe_asset_id,
            "filename": f"{filename_stem}-page-{page_number}-image-{image_index}.{extension}",
            "mime_type": mime_type,
            "extension": extension,
            "page": page_number,
            "image_index": image_index,
            "width": width,
            "height": height,
            "size_bytes": len(image_bytes),
            "sha256": digest,
            "status": "pending_review",
            "source": source,
            "admin_only": True,
            "storage": "extraction_metadata",
            "has_content": False,
        }
        if len(image_bytes) <= max_inline_bytes:
            asset["content_base64"] = base64.b64encode(image_bytes).decode("ascii")
            asset["has_content"] = True
        return asset

    assets: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    filename_stem = PurePosixPath(str(filename or "training-material.pdf")).stem or "training-material"

    try:
        import fitz  # type: ignore
    except Exception:
        fitz = None  # type: ignore
    if fitz is not None:
        with fitz.open(stream=data, filetype="pdf") as document:
            for page_number, page in enumerate(document, start=1):
                for image_index, image_ref in enumerate(page.get_images(full=True), start=1):
                    if len(assets) >= max_assets:
                        return assets
                    xref = image_ref[0]
                    try:
                        image_info = document.extract_image(xref)
                    except Exception:
                        continue
                    image_bytes = image_info.get("image") or b""
                    if not image_bytes:
                        continue
                    extension = str(image_info.get("ext") or "png").lower().replace("jpg", "jpeg")
                    mime_type = "image/jpeg" if extension in {"jpeg", "jpg"} else f"image/{extension}"
                    asset = _asset_from_image_bytes(
                        image_bytes=image_bytes,
                        page_number=page_number,
                        image_index=image_index,
                        extension=extension,
                        mime_type=mime_type,
                        width=image_info.get("width"),
                        height=image_info.get("height"),
                        source="pdf_embedded_image",
                    )
                    if asset:
                        assets.append(asset)
        if assets:
            return assets

    try:
        import pypdfium2 as pdfium  # type: ignore

        document = pdfium.PdfDocument(data)
        for page_index in range(len(document)):
            if len(assets) >= max_assets:
                return assets
            page_number = page_index + 1
            try:
                page = document[page_index]
                bitmap = page.render(scale=1.5)
                image = bitmap.to_pil().convert("RGB")
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=82, optimize=True)
                image_bytes = buffer.getvalue()
                asset = _asset_from_image_bytes(
                    image_bytes=image_bytes,
                    page_number=page_number,
                    image_index=1,
                    extension="jpeg",
                    mime_type="image/jpeg",
                    width=image.width,
                    height=image.height,
                    source="pdf_rendered_page",
                )
                if asset:
                    asset["filename"] = f"{filename_stem}-page-{page_number}.jpeg"
                    asset["review_note"] = "Страница PDF отрендерена как визуал учебного материала."
                    assets.append(asset)
            except Exception:
                continue
    except Exception:
        return assets
    return assets


def build_training_material_payload(material: Any, *, include_internal: bool = False) -> dict[str, Any]:
    extraction = _dict_value(material, "extraction_metadata", {}) or _dict_value(material, "extraction", {}) or {}
    safe_extraction = dict(extraction) if isinstance(extraction, dict) else {}
    if safe_extraction.get("source_file"):
        safe_extraction["source_file"] = build_training_material_source_file_payload(safe_extraction, include_content=False)
    if safe_extraction.get("visual_assets"):
        safe_extraction["visual_assets"] = build_training_material_visual_assets_payload(safe_extraction, include_content=False)
    if not include_internal:
        safe_extraction.pop("source_file", None)
        safe_extraction.pop("visual_assets", None)
        safe_extraction.pop("visual_assets_summary", None)
        if isinstance(safe_extraction.get("warnings"), list):
            safe_extraction["warnings"] = [warning for warning in safe_extraction["warnings"] if warning not in {"visual_assets_pending_review", "source_file_too_large_for_inline_storage"}]
    payload = {
        "id": str(_dict_value(material, "id")),
        "title": _dict_value(material, "title"),
        "topic": _dict_value(material, "topic") or "Общее",
        "category": _dict_value(material, "category") or "Библиотека GLAME",
        "description": _dict_value(material, "description"),
        "markdown_content": _dict_value(material, "markdown_content") or _dict_value(material, "content") or "",
        "content_format": "markdown",
        "status": normalize_training_material_status(_dict_value(material, "status")),
        "tags": _dict_value(material, "tags", []) or [],
        "source_type": _dict_value(material, "source_type") or "manual_md",
        "extraction": safe_extraction,
        "program_code": _dict_value(material, "program_code"),
        "competencies": _dict_value(material, "competencies", []) or [],
        "order_index": int(_dict_value(material, "order_index", 100) or 100),
        "created_at": _dict_value(material, "created_at"),
        "updated_at": _dict_value(material, "updated_at"),
    }
    if payload.get("program_code") == "trainee_base" and payload.get("topic") in {"Тренды и стилизация", "Стилистический подбор", "Бренд и сервис GLAME", "Общее"}:
        corrected = enrich_training_material_import_metadata(
            {
                "title": payload.get("title"),
                "topic": "Общее",
                "category": "Библиотека GLAME",
                "description": payload.get("description"),
                "markdown_content": payload.get("markdown_content"),
                "tags": [],
                "competencies": [],
                "program_code": "trainee_base",
                "extraction": safe_extraction,
            },
            default_program_code="trainee_base",
        )
        payload["topic"] = corrected.get("topic") or payload["topic"]
        payload["category"] = corrected.get("category") or payload["category"]
        payload["tags"] = corrected.get("tags") or []
        payload["competencies"] = corrected.get("competencies") or []
        if isinstance(payload.get("extraction"), dict):
            payload["extraction"] = {**payload["extraction"], "auto_recognized": corrected.get("extraction", {}).get("auto_recognized", {})}
    if include_internal:
        source_file_payload = build_training_material_source_file_payload(extraction, include_content=False)
        visual_assets_payload = build_training_material_visual_assets_payload(extraction, include_content=False)
        payload.update(
            {
                "internal_notes": _dict_value(material, "internal_notes"),
                "created_by_user_id": str(_dict_value(material, "created_by_user_id")) if _dict_value(material, "created_by_user_id") else None,
                "approved_by_user_id": str(_dict_value(material, "approved_by_user_id")) if _dict_value(material, "approved_by_user_id") else None,
                "approved_at": _dict_value(material, "approved_at"),
                "source_file": source_file_payload,
                "visual_assets": visual_assets_payload,
                "visual_assets_summary": extraction.get("visual_assets_summary") if isinstance(extraction, dict) else None,
            }
        )
    return payload


def _markdown_preview_html(markdown: str | None) -> str:
    lines = (markdown or "").splitlines()
    html_lines: list[str] = []
    in_list = False
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{html.escape(stripped)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def build_training_material_status_history_payload(history: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in history or []:
        items.append(
            {
                "id": str(_dict_value(event, "id")),
                "material_id": str(_dict_value(event, "material_id")) if _dict_value(event, "material_id") else None,
                "from_status": normalize_training_material_status(_dict_value(event, "from_status")) if _dict_value(event, "from_status") else None,
                "to_status": normalize_training_material_status(_dict_value(event, "to_status")),
                "note": _dict_value(event, "note"),
                "changed_by_user_id": str(_dict_value(event, "changed_by_user_id")) if _dict_value(event, "changed_by_user_id") else None,
                "created_at": _dict_value(event, "created_at"),
            }
        )
    return items


def build_training_material_detail_payload(material: Any, *, history: list[Any] | None = None) -> dict[str, Any]:
    material_payload = build_training_material_payload(material, include_internal=True)
    history_payload = build_training_material_status_history_payload(history or [])
    return {
        "material": material_payload,
        "preview_html": _markdown_preview_html(material_payload.get("markdown_content") or ""),
        "history": history_payload,
        "history_summary": {
            "events": len(history_payload),
            "last_status": history_payload[0].get("to_status") if history_payload else material_payload.get("status"),
        },
    }


def build_training_material_status_change_payload(*, material: Any, new_status: str, changed_by_user_id: Any | None = None, note: str | None = None) -> dict[str, Any]:
    from_status = normalize_training_material_status(_dict_value(material, "status"))
    to_status = normalize_training_material_status(new_status)
    return {
        "material_id": str(_dict_value(material, "id")) if _dict_value(material, "id") else None,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by_user_id": str(changed_by_user_id) if changed_by_user_id else None,
        "note": (note or "").strip() or None,
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "requires_seller_visibility_check": to_status == "published" and from_status != "published",
    }


def build_training_material_publish_cascade_payload(
    *,
    material: Any,
    slides: list[Any] | None = None,
    extraction_metadata: dict[str, Any] | None = None,
    reviewed_by_user_id: Any | None = None,
) -> dict[str, Any]:
    """Return side effects needed when an admin publishes the whole material.

    Material-level publish is the manager approval boundary. Once a manager presses
    "publish" for the material, seller-visible pages/slides should not remain
    draft/review one by one. Rejected visual assets stay rejected; attached/used
    visual assets become approved/attached in admin metadata.
    """
    if normalize_training_material_status(_dict_value(material, "status")) != "published":
        return {
            "slides_to_publish": [],
            "published_slides_count": 0,
            "extraction_metadata": extraction_metadata or {},
            "visual_assets_summary": (extraction_metadata or {}).get("visual_assets_summary") or {},
        }

    slides_to_publish: list[str] = []
    slide_image_urls: set[str] = set()
    slide_ids_with_images: set[str] = set()
    for slide in slides or []:
        slide_id = str(_dict_value(slide, "id")) if _dict_value(slide, "id") else ""
        if normalize_training_material_status(_dict_value(slide, "status")) != "published" and slide_id:
            slides_to_publish.append(slide_id)
        image_url = _dict_value(slide, "image_url")
        if image_url:
            slide_image_urls.add(str(image_url))
            if slide_id:
                slide_ids_with_images.add(slide_id)

    extraction = dict(extraction_metadata or {})
    raw_assets = list(extraction.get("visual_assets") or [])
    updated_assets: list[Any] = []
    now = datetime.now(timezone.utc).isoformat()
    summary = {"total": 0, "pending_review": 0, "approved": 0, "rejected": 0, "attached": 0}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            updated_assets.append(raw_asset)
            continue
        asset = dict(raw_asset)
        status = str(asset.get("status") or "pending_review")
        if status != "rejected":
            attached_slide_id = str(asset.get("attached_slide_id") or "")
            asset_image_url = str(asset.get("image_url") or "")
            if attached_slide_id or (asset_image_url and asset_image_url in slide_image_urls):
                asset["status"] = "attached" if attached_slide_id in slide_ids_with_images or attached_slide_id else "approved"
            else:
                asset["status"] = "approved"
            asset["review_note"] = asset.get("review_note") or "Опубликовано вместе с материалом"
            if reviewed_by_user_id:
                asset["reviewed_by_user_id"] = str(reviewed_by_user_id)
            asset["reviewed_at"] = asset.get("reviewed_at") or now
        updated_assets.append(asset)
        summary["total"] += 1
        status = str(asset.get("status") or "pending_review")
        if status in summary:
            summary[status] += 1
    if raw_assets:
        extraction["visual_assets"] = updated_assets
        extraction["visual_assets_summary"] = summary

    return {
        "slides_to_publish": slides_to_publish,
        "published_slides_count": len(slides_to_publish),
        "extraction_metadata": extraction,
        "visual_assets_summary": summary if raw_assets else extraction.get("visual_assets_summary") or {},
    }


def build_training_material_slide_payload(slide: Any, *, include_internal: bool = False) -> dict[str, Any]:
    payload = {
        "id": str(_dict_value(slide, "id")),
        "material_id": str(_dict_value(slide, "material_id")) if _dict_value(slide, "material_id") else None,
        "title": _dict_value(slide, "title"),
        "body": _dict_value(slide, "body") or "",
        "image_url": _dict_value(slide, "image_url"),
        "quiz_question": _dict_value(slide, "quiz_question"),
        "order_index": int(_dict_value(slide, "order_index", 100) or 100),
        "status": normalize_training_material_status(_dict_value(slide, "status")),
        "content_format": "learning_slide",
        "created_at": _dict_value(slide, "created_at"),
        "updated_at": _dict_value(slide, "updated_at"),
    }
    if include_internal:
        payload.update(
            {
                "image_prompt": _dict_value(slide, "image_prompt"),
                "speaker_note": _dict_value(slide, "speaker_note"),
                "meta": _dict_value(slide, "meta", {}) or {},
            }
        )
    return payload


def build_training_material_slides_payload(slides: list[Any], *, seller_safe: bool = True) -> dict[str, Any]:
    visible_slides = [slide for slide in slides or [] if not seller_safe or normalize_training_material_status(_dict_value(slide, "status")) == "published"]
    ordered_slides = sorted(visible_slides, key=lambda slide: (int(_dict_value(slide, "order_index", 100) or 100), str(_dict_value(slide, "title") or "")))
    slide_payloads = [build_training_material_slide_payload(slide, include_internal=not seller_safe) for slide in ordered_slides]
    return {
        "slides": slide_payloads,
        "summary": {
            "slides": len(slide_payloads),
            "seller_safe": seller_safe,
            "has_quiz": any(slide.get("quiz_question") for slide in slide_payloads),
        },
    }


def build_training_material_slide_progress_payload(progress: Any | None) -> dict[str, Any]:
    if not progress:
        return {"viewed": False, "completed": False, "viewed_at": None, "completed_at": None}
    return {
        "id": str(_dict_value(progress, "id")) if _dict_value(progress, "id") else None,
        "material_id": str(_dict_value(progress, "material_id")) if _dict_value(progress, "material_id") else None,
        "slide_id": str(_dict_value(progress, "slide_id")) if _dict_value(progress, "slide_id") else None,
        "viewed": bool(_dict_value(progress, "viewed_at") or _dict_value(progress, "completed_at")),
        "completed": bool(_dict_value(progress, "completed_at")),
        "viewed_at": _dict_value(progress, "viewed_at"),
        "completed_at": _dict_value(progress, "completed_at"),
    }


def build_training_material_slides_progress_payload(
    *,
    slides: list[Any],
    progress_records: list[Any] | None = None,
    seller_safe: bool = True,
) -> dict[str, Any]:
    progress_by_slide = {str(_dict_value(record, "slide_id")): record for record in progress_records or []}
    payload = build_training_material_slides_payload(slides, seller_safe=seller_safe)
    completed_slides = 0
    for slide in payload["slides"]:
        progress_payload = build_training_material_slide_progress_payload(progress_by_slide.get(str(slide.get("id"))))
        slide["progress"] = progress_payload
        if progress_payload.get("completed"):
            completed_slides += 1
    total_slides = len(payload["slides"])
    progress_percent = int(round((completed_slides / total_slides) * 100)) if total_slides else 0
    payload["summary"].update(
        {
            "completed_slides": completed_slides,
            "progress_percent": progress_percent,
            "material_completed": bool(total_slides and completed_slides >= total_slides),
        }
    )
    return payload


def _learning_pack_sentences(markdown: str) -> list[str]:
    cleaned_lines: list[str] = []
    for raw_line in (markdown or "").splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line.lstrip("-").strip()
        cleaned_lines.append(line)
    text = " ".join(cleaned_lines)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _material_extraction(material: Any) -> dict[str, Any]:
    extraction = _dict_value(material, "extraction_metadata", None) or _dict_value(material, "extraction", None) or {}
    return extraction if isinstance(extraction, dict) else {}


def build_document_extractor_status_payload(
    *,
    python_modules: dict[str, bool] | None = None,
    commands: dict[str, bool] | None = None,
    free_disk_gb: float | None = None,
) -> dict[str, Any]:
    modules = python_modules if python_modules is not None else {
        "pdfplumber": importlib.util.find_spec("pdfplumber") is not None,
        "pypdf2": importlib.util.find_spec("PyPDF2") is not None,
        "fitz": importlib.util.find_spec("fitz") is not None,
        "pymupdf4llm": importlib.util.find_spec("pymupdf4llm") is not None,
        "marker": importlib.util.find_spec("marker") is not None,
        "docx": importlib.util.find_spec("docx") is not None,
    }
    command_status = commands if commands is not None else {
        "soffice": shutil.which("soffice") is not None or shutil.which("libreoffice") is not None,
        "antiword": shutil.which("antiword") is not None,
        "tesseract": shutil.which("tesseract") is not None,
    }
    if free_disk_gb is None:
        try:
            usage = shutil.disk_usage("/")
            free_disk_gb = round(usage.free / (1024 ** 3), 2)
        except Exception:
            free_disk_gb = None
    marker_available = bool(modules.get("marker"))
    marker_ready = marker_available and (free_disk_gb is None or free_disk_gb >= 5)
    warnings: list[str] = []
    if not marker_ready:
        warnings.append("marker_pdf_not_ready_for_scanned_ocr")
    if not command_status.get("soffice"):
        warnings.append("libreoffice_missing_for_legacy_doc_conversion")
    if not command_status.get("tesseract"):
        warnings.append("tesseract_missing_for_lightweight_ocr")
    supported = ["md", "markdown", "txt", "text", "docx", "pdf"]
    if command_status.get("soffice") or command_status.get("antiword"):
        supported.append("doc")
    text_pdf_ready = bool(modules.get("pdfplumber") or modules.get("pypdf2") or modules.get("fitz"))
    recommendation = "advanced_ocr_ready" if marker_ready else "lightweight_text_extraction_ready" if text_pdf_ready else "manual_review_only"
    return {
        "summary": {"ready": bool(text_pdf_ready or marker_ready or modules.get("docx")), "free_disk_gb": free_disk_gb},
        "extractors": {
            "pdfplumber": {"available": bool(modules.get("pdfplumber")), "purpose": "PDF с текстовым слоем, основной extractor"},
            "pypdf2": {"available": bool(modules.get("pypdf2")), "purpose": "PDF text fallback"},
            "pymupdf": {"available": bool(modules.get("fitz")), "purpose": "PDF с текстовым слоем"},
            "pymupdf4llm": {"available": bool(modules.get("pymupdf4llm")), "purpose": "Markdown layout для PDF"},
            "marker_pdf": {"available": marker_ready, "installed": marker_available, "purpose": "OCR/сложная верстка, требует ~5GB"},
            "docx_builtin": {"available": True, "purpose": "DOCX через zip/xml fallback"},
            "libreoffice": {"available": bool(command_status.get("soffice")), "purpose": "legacy DOC/DOCX conversion"},
            "antiword": {"available": bool(command_status.get("antiword")), "purpose": "legacy DOC text fallback"},
            "tesseract": {"available": bool(command_status.get("tesseract")), "purpose": "легкий OCR, если отдельно подключен"},
        },
        "supported_extensions": supported,
        "warnings": warnings,
        "recommendation": recommendation,
    }


def build_training_material_retry_extraction_payload(
    *,
    material: Any,
    filename: str,
    extracted_text: str,
    extractor: str,
    reviewed_by_user_id: Any,
    note: str | None = None,
) -> dict[str, Any]:
    markdown = _normalize_import_text_to_markdown(filename=filename, text=extracted_text or "")
    if not markdown:
        raise ValueError("empty_extraction_result")
    diagnostics = build_training_document_extraction_diagnostics(filename=filename, extracted_text=extracted_text, extractor=extractor)
    review = build_training_material_extraction_review_payload(
        material=material,
        reviewed_markdown=markdown,
        reviewed_by_user_id=reviewed_by_user_id,
        note=note or f"Повторное извлечение через {extractor}",
    )
    review["extraction_metadata"] = {
        **review["extraction_metadata"],
        **diagnostics,
        "quality": "reviewed",
        "ocr_required": False,
        "warnings": [],
        "extraction_reviewed": True,
        "retry_extractor": extractor,
    }
    review["publish_gate"] = build_training_material_publish_gate_payload({**(_dict_value(material, "__dict__", {}) or {}), **review}, target_status="published")
    return review


def build_training_material_publish_gate_payload(material: Any, *, target_status: str | None = None) -> dict[str, Any]:
    status = normalize_training_material_status(target_status or _dict_value(material, "status"))
    extraction = _material_extraction(material)
    warnings = extraction.get("warnings") or []
    quality = str(extraction.get("quality") or "").lower()
    needs_review = bool(extraction.get("ocr_required")) or quality in {"needs_ocr", "low"} or "ocr_required" in warnings
    reviewed = bool(extraction.get("extraction_reviewed")) or quality == "reviewed"
    if status == "published" and needs_review and not reviewed:
        return {
            "can_publish": False,
            "blocked_reason": "extraction_review_required",
            "quality": quality or None,
            "warnings": warnings,
            "manager_message": "Перед публикацией нужен OCR/ручная проверка текста: материал импортирован из файла с низким качеством извлечения.",
        }
    return {
        "can_publish": True,
        "blocked_reason": None,
        "quality": quality or extraction.get("quality"),
        "warnings": warnings,
        "manager_message": "Материал можно переводить в выбранный статус после методической проверки.",
    }


def build_training_material_extraction_review_payload(*, material: Any, reviewed_markdown: str, reviewed_by_user_id: Any, note: str | None = None) -> dict[str, Any]:
    markdown = (reviewed_markdown or "").strip()
    if not markdown:
        raise ValueError("reviewed_markdown_required")
    previous = _material_extraction(material)
    extraction = {
        **previous,
        "quality": "reviewed",
        "ocr_required": False,
        "warnings": [],
        "extraction_reviewed": True,
        "reviewed_by_user_id": str(reviewed_by_user_id) if reviewed_by_user_id else None,
        "review_note": note,
    }
    internal_notes = "\n".join(
        part
        for part in [
            _dict_value(material, "internal_notes"),
            f"Extraction/OCR review: текст вручную проверен пользователем {reviewed_by_user_id}. {note or ''}".strip(),
        ]
        if part
    )
    return {"markdown_content": markdown, "extraction_metadata": extraction, "internal_notes": internal_notes}


def _training_material_sections(markdown: str) -> list[dict[str, str]]:
    lines = (markdown or "").splitlines()
    sections: list[dict[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if current_title:
            body = "\n".join(line.strip() for line in current_lines if line.strip()).strip()
            sections.append({"title": current_title.strip(), "body": body})
        current_title = None
        current_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue
        heading = re.match(r"^(?:#{1,3}\s*)?(\d{1,2}\.\s+.{4,160})$", line)
        if heading:
            flush()
            current_title = heading.group(1).strip()
            continue
        if current_title:
            current_lines.append(line)
    flush()
    return [section for section in sections if section.get("title") or section.get("body")]


def _training_visual_assets_for_learning(material: Any) -> list[dict[str, Any]]:
    extraction = _material_extraction(material)
    assets = build_training_material_visual_assets_payload(extraction, include_content=True)
    assets = [asset for asset in assets if asset.get("image_url")]
    assets.sort(key=lambda item: (int(item.get("page") or 9999), int(item.get("image_index") or 9999), str(item.get("asset_id") or "")))
    return assets


def _infer_training_quiz_question(slide_title: str, body: str, index: int) -> str:
    text = f"{slide_title} {body}".lower()
    if "практик" in text or "задание" in text:
        return "Выполните практику из слайда: какое украшение выберете, какой эффект на образ объясните и какой фразой скажете это клиенту?"
    if "как говорить" in text or "фраз" in text or "клиент" in text:
        return "Сформулируйте GLAME-фразу без анализа внешности клиента: что изменилось в образе и почему это красиво?"
    if "ошиб" in text or "не используем" in text:
        return "Какие формулировки нельзя говорить клиенту и какой мягкой GLAME-фразой их заменить?"
    if "форма" in text or "лиц" in text:
        return "Как использовать эту схему как внутреннюю подсказку, не называя форму лица клиенту вслух?"
    if "контроль" in text or "вопрос" in text or index >= 6:
        return "Ответьте на контрольный вопрос: какой принцип из материала вы примените на смене сегодня?"
    return "Что главное нужно применить в работе после этого слайда?"


def build_training_material_question_pool(*, title: str, topic: str, sentences: list[str], slide_questions: list[str] | None = None, target_count: int = 10) -> list[dict[str, Any]]:
    """Build manager-reviewed draft questions for knowledge assessment from a training material."""
    base_facts = [re.sub(r"\s+", " ", item).strip() for item in (sentences or []) if str(item).strip()]
    if not base_facts:
        base_facts = [title, topic]
    slide_questions = [str(item).strip() for item in (slide_questions or []) if str(item).strip()]
    templates = [
        ("short_answer", "easy", "Назовите главную мысль урока «{topic}».", "Проверить, что продавец понял ключевой принцип материала и может сформулировать его своими словами."),
        ("client_scenario", "medium", "Клиент сомневается. Как объяснить правило из материала спокойной GLAME-фразой без давления?", "В ответе есть ситуация клиента, мягкая формулировка, польза/эффект и отсутствие давления."),
        ("do_dont", "medium", "Какие две формулировки из этой темы нельзя говорить клиенту и чем их заменить?", "Продавец различает внутреннюю подсказку и клиентский язык, не оценивает внешность и не дожимает."),
        ("shift_application", "medium", "Что конкретно вы примените в ближайшей смене по теме «{topic}»?", "Есть действие в зале, пример изделия/сервиса и фраза для клиента."),
        ("manager_check", "hard", "Разберите мини-кейс по материалу: что заметить, что предложить и как объяснить клиенту?", "Ответ структурирован: наблюдение → предложение → GLAME-фраза → следующий деликатный шаг."),
    ]
    questions: list[dict[str, Any]] = []
    for question in slide_questions:
        questions.append({
            "question": question,
            "type": "slide_self_check",
            "difficulty": "easy",
            "expected_answer": "Ответ должен опираться на конкретный слайд и показывать, как продавец применит правило в работе.",
            "criteria": ["понимание слайда", "конкретика", "язык GLAME без давления"],
            "source": "slide_quiz_question",
        })
    for index in range(max(0, target_count - len(questions))):
        q_type, difficulty, question_template, expected = templates[index % len(templates)]
        fact = base_facts[min(index, len(base_facts) - 1)]
        questions.append({
            "question": question_template.format(topic=topic),
            "type": q_type,
            "difficulty": difficulty,
            "expected_answer": expected,
            "criteria": ["понимание материала", "конкретный пример", "корректная GLAME-формулировка"],
            "source_excerpt": fact[:240],
        })
    return questions[: max(6, min(int(target_count or 10), 12))]


def build_training_material_learning_pack_payload(*, material: Any, target_slide_count: int = 5) -> dict[str, Any]:
    gate = build_training_material_publish_gate_payload(material, target_status="published")
    if not gate.get("can_publish"):
        return {
            "status": "blocked_extraction_review_required",
            "review_required": True,
            "source": {"type": _dict_value(material, "source_type") or "material_markdown", "material_id": str(_dict_value(material, "id")) if _dict_value(material, "id") else None},
            "material": build_training_material_payload(material, include_internal=True),
            "slides": [],
            "practice": {},
            "assessment": {"manager_review_note": gate.get("manager_message"), "question_pool": []},
            "extraction_gate": gate,
            "message": gate.get("manager_message"),
        }
    material_payload = build_training_material_payload(material, include_internal=True)
    markdown = material_payload.get("markdown_content") or ""
    title = material_payload.get("title") or "Учебный материал"
    topic = material_payload.get("topic") or "Общее"
    sentences = _learning_pack_sentences(markdown)
    if not sentences:
        sentences = [str(title), "Сформулируйте ключевую мысль урока в GLAME-языке."]
    sections = _training_material_sections(markdown)
    visual_assets = _training_visual_assets_for_learning(material)

    slide_count = max(3, min(int(target_slide_count or 5), 7))
    if sections:
        section_slides = sections[:slide_count]
        slide_titles = [section["title"][:120] for section in section_slides]
    else:
        section_slides = []
        slide_titles = [
            f"1. Идея: {title}",
            "2. Почему это важно клиенту",
            "3. Регламент действия продавца",
            "4. GLAME-фраза для клиента",
            "5. Практика на смене",
            "6. Самопроверка",
            "7. Передача руководителю",
        ][:slide_count]
    slides: list[dict[str, Any]] = []
    for index, slide_title in enumerate(slide_titles, start=1):
        section = section_slides[index - 1] if index - 1 < len(section_slides) else None
        source_text = (section or {}).get("body") or sentences[min(index - 1, len(sentences) - 1)]
        source_text = re.sub(r"\s+", " ", source_text).strip()
        if section:
            body = source_text[:900] + ("..." if len(source_text) > 900 else "")
        elif index == 1:
            body = f"Ключевая мысль материала: {source_text}"
        elif index == 2:
            body = f"Объясните клиентскую пользу без давления: {source_text}"
        elif index == 3:
            body = f"Действие в зале: наблюдать ситуацию клиента, выбрать конкретное украшение и объяснить эффект на образ. Основа: {source_text}"
        elif index == 4:
            body = f"Сформулируйте спокойную GLAME-фразу: «{source_text}»"
        elif index == 5:
            body = "В смене выберите 1 конкретное изделие, примените правило из материала и запишите клиентскую фразу."
        elif index == 6:
            body = "Проверьте себя: есть ли конкретное изделие, эффект на образ и мягкая профессиональная формулировка?"
        else:
            body = "Передайте результат на проверку руководителю; AI может помочь с черновиком, но итог подтверждает руководитель."
        visual_asset = visual_assets[index - 1] if index - 1 < len(visual_assets) else None
        slides.append(
            {
                "title": slide_title,
                "body": body,
                "image_url": visual_asset.get("image_url") if visual_asset else None,
                "image_prompt": None if visual_asset else f"GLAME premium jewelry training visual, тема: {topic}, слайд {index}, clean editorial style",
                "speaker_note": f"Для руководителя: руководитель проверяет, что слайд {index} соответствует стандарту GLAME и не содержит давления/оценок внешности.",
                "quiz_question": _infer_training_quiz_question(slide_title, body, index),
                "status": "draft",
                "order_index": index * 10,
                "content_format": "learning_slide",
                "meta": {
                    "visual_asset_id": visual_asset.get("asset_id") if visual_asset else None,
                    "visual_asset_source": visual_asset.get("source") if visual_asset else None,
                    "source_pdf_page": visual_asset.get("page") if visual_asset else None,
                    "review_required": True,
                },
            }
        )

    question_pool = build_training_material_question_pool(
        title=str(title),
        topic=str(topic),
        sentences=sentences,
        slide_questions=[slide.get("quiz_question") for slide in slides],
        target_count=10,
    )

    return {
        "status": "draft_review_required",
        "review_required": True,
        "source": {"type": material_payload.get("source_type") or "material_markdown", "material_id": material_payload.get("id")},
        "material": material_payload,
        "slides": slides,
        "practice": {
            "task": f"Выберите конкретное украшение GLAME по теме «{topic}», примените правило из материала и напишите фразу для клиента: что украшение дает образу, с чем его носить и почему это подходит ситуации клиента.",
            "answer_template": ["Изделие", "Ситуация клиента", "Эффект на образ", "Фраза продавца", "Следующий деликатный шаг"],
        },
        "assessment": {
            "criteria": [
                "понимание темы урока",
                "конкретное изделие/пример вместо общих слов",
                "эффект украшения на образ",
                "спокойный GLAME-язык без давления",
                "применимость в смене",
            ],
            "manager_review_note": "AI формирует только draft learning pack. Руководитель проверяет слайды, практику, пул вопросов и критерии перед публикацией.",
            "question_pool": question_pool,
        },
    }


def build_step_material_link_payload(link: Any, *, material: Any | None = None, include_internal: bool = False) -> dict[str, Any]:
    payload = {
        "id": str(_dict_value(link, "id")),
        "program_id": str(_dict_value(link, "program_id")) if _dict_value(link, "program_id") else None,
        "module_id": str(_dict_value(link, "module_id")) if _dict_value(link, "module_id") else None,
        "step_id": str(_dict_value(link, "step_id")) if _dict_value(link, "step_id") else None,
        "material_id": str(_dict_value(link, "material_id")) if _dict_value(link, "material_id") else None,
        "role": _dict_value(link, "role") or "primary_lesson",
        "required_to_complete": bool(_dict_value(link, "required_to_complete", True)),
        "order_index": int(_dict_value(link, "order_index", 100) or 100),
    }
    if include_internal:
        payload["meta"] = _dict_value(link, "meta", {}) or {}
    if material is not None:
        material_payload = build_training_material_payload(material, include_internal=include_internal)
        payload["material"] = material_payload
        payload["title"] = material_payload.get("title")
        payload["topic"] = material_payload.get("topic")
        payload["status"] = material_payload.get("status")
    return payload


def _step_status(step_id: str, step_progress: dict[str, Any]) -> str:
    progress = step_progress.get(step_id) or {}
    if isinstance(progress, str):
        return progress
    return str(progress.get("status") or "available")


def build_step_material_practice_gate_payload(
    *,
    step_materials: list[Any],
    material_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    progress_by_material = material_progress or {}
    required_materials = [item for item in step_materials or [] if bool(_dict_value(item, "required_to_complete", True))]
    blocked_materials: list[dict[str, Any]] = []
    completed_required = 0
    for item in required_materials:
        material_id = str(_dict_value(item, "material_id")) if _dict_value(item, "material_id") else None
        progress = progress_by_material.get(material_id or "") or {}
        slides_count = int(progress.get("slides") or 0)
        completed_slides = int(progress.get("completed_slides") or 0)
        is_completed = bool(progress.get("material_completed"))
        if is_completed:
            completed_required += 1
        else:
            blocked_materials.append(
                {
                    "material_id": material_id,
                    "title": _dict_value(item, "title") or _dict_value(item, "material", {}).get("title") if isinstance(_dict_value(item, "material"), dict) else _dict_value(item, "title"),
                    "role": _dict_value(item, "role") or "primary_lesson",
                    "slides": slides_count,
                    "completed_slides": completed_slides,
                    "progress_percent": int(progress.get("progress_percent") or 0),
                }
            )
    can_start = not blocked_materials
    return {
        "can_start_practice": can_start,
        "blocked_reason": None if can_start else "complete_required_material_slides",
        "required_materials": len(required_materials),
        "completed_required_materials": completed_required,
        "blocked_materials": blocked_materials,
        "next_action": "start_practice" if can_start else "study_required_materials",
    }


def build_training_material_progress_analytics_payload(
    *,
    materials: list[Any],
    slides: list[Any],
    progress_records: list[Any] | None = None,
    sellers: list[Any] | None = None,
    step_material_links: list[Any] | None = None,
    programs: list[Any] | None = None,
    enrollments: list[Any] | None = None,
    step_submissions: list[Any] | None = None,
) -> dict[str, Any]:
    published_materials = [item for item in materials or [] if normalize_training_material_status(_dict_value(item, "status")) == "published"]
    material_by_id = {str(_dict_value(item, "id")): item for item in published_materials}
    published_slides_by_material: dict[str, list[Any]] = {material_id: [] for material_id in material_by_id}
    for slide in slides or []:
        material_id = str(_dict_value(slide, "material_id")) if _dict_value(slide, "material_id") else ""
        if material_id in material_by_id and normalize_training_material_status(_dict_value(slide, "status")) == "published":
            published_slides_by_material.setdefault(material_id, []).append(slide)

    seller_ids = {str(_dict_value(seller, "id")) for seller in sellers or [] if _dict_value(seller, "id")}
    for record in progress_records or []:
        if _dict_value(record, "seller_user_id"):
            seller_ids.add(str(_dict_value(record, "seller_user_id")))
    active_learners = len(seller_ids)

    required_material_ids = {
        str(_dict_value(link, "material_id"))
        for link in step_material_links or []
        if _dict_value(link, "material_id") and bool(_dict_value(link, "required_to_complete", True))
    }
    completed_slides_by_material_seller: dict[tuple[str, str], set[str]] = {}
    viewed_slides_by_material_seller: dict[tuple[str, str], set[str]] = {}
    for record in progress_records or []:
        material_id = str(_dict_value(record, "material_id")) if _dict_value(record, "material_id") else ""
        seller_id = str(_dict_value(record, "seller_user_id")) if _dict_value(record, "seller_user_id") else ""
        slide_id = str(_dict_value(record, "slide_id")) if _dict_value(record, "slide_id") else ""
        if material_id not in material_by_id or not seller_id or not slide_id:
            continue
        if _dict_value(record, "viewed_at") or _dict_value(record, "completed_at"):
            viewed_slides_by_material_seller.setdefault((material_id, seller_id), set()).add(slide_id)
        if _dict_value(record, "completed_at"):
            completed_slides_by_material_seller.setdefault((material_id, seller_id), set()).add(slide_id)

    material_rows: list[dict[str, Any]] = []
    total_completed_instances = 0
    blocked_materials = 0
    for material_id, material in material_by_id.items():
        slide_ids = {str(_dict_value(slide, "id")) for slide in published_slides_by_material.get(material_id, []) if _dict_value(slide, "id")}
        total_slides = len(slide_ids)
        completed_instances = 0
        started_learners = 0
        average_slide_progress_values: list[int] = []
        for seller_id in seller_ids:
            viewed = viewed_slides_by_material_seller.get((material_id, seller_id), set())
            completed = completed_slides_by_material_seller.get((material_id, seller_id), set())
            if viewed or completed:
                started_learners += 1
            seller_percent = int(round((len(completed & slide_ids) / total_slides) * 100)) if total_slides else 100
            average_slide_progress_values.append(seller_percent)
            if total_slides and slide_ids.issubset(completed):
                completed_instances += 1
            elif total_slides == 0:
                completed_instances += 1
        total_completed_instances += completed_instances
        completion_percent = int(round((completed_instances / active_learners) * 100)) if active_learners else 0
        average_slide_progress = int(round(sum(average_slide_progress_values) / len(average_slide_progress_values))) if average_slide_progress_values else 0
        is_required = material_id in required_material_ids
        risk_level = "low"
        if is_required and average_slide_progress < 60:
            risk_level = "high"
            blocked_materials += 1
        elif completion_percent < 80:
            risk_level = "medium"
        material_rows.append(
            {
                "material_id": material_id,
                "title": _dict_value(material, "title"),
                "topic": _dict_value(material, "topic"),
                "category": _dict_value(material, "category"),
                "required_to_complete": is_required,
                "slides": total_slides,
                "started_learners": started_learners,
                "completed_learners": completed_instances,
                "completion_percent": completion_percent,
                "average_slide_progress": average_slide_progress,
                "risk_level": risk_level,
                "manager_action": "Проверить, почему продавцы не доходят до практики по материалу" if risk_level == "high" else "Контролировать динамику изучения",
            }
        )

    material_rows.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(item["risk_level"], 3), item["completion_percent"], str(item.get("title") or "")), reverse=False)
    recommendations: list[dict[str, str]] = []
    if material_rows and material_rows[0]["risk_level"] in {"high", "medium"}:
        bottleneck = material_rows[0]
        recommendations.append(
            {
                "type": "material_bottleneck",
                "title": "Разобрать учебный bottleneck",
                "text": f"Материал «{bottleneck.get('title') or 'без названия'}» прошли только {bottleneck.get('completion_percent')}% активных продавцов. Проверьте понятность слайдов и назначьте короткий coaching/напоминание.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "type": "stable_progress",
                "title": "Прогресс материалов стабильный",
                "text": "Критичных блокировок по изучению опубликованных материалов сейчас нет.",
            }
        )

    def _score_to_percent(value: Any) -> int | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric <= 10:
            numeric *= 10
        return max(0, min(100, int(round(numeric))))

    program_by_id = {str(_dict_value(program, "id")): program for program in programs or [] if _dict_value(program, "id")}
    material_count_by_program: dict[str, int] = {}
    for material in published_materials:
        program_code = str(_dict_value(material, "program_code") or "")
        if program_code:
            material_count_by_program[program_code] = material_count_by_program.get(program_code, 0) + 1

    enrollments_by_program: dict[str, list[Any]] = {}
    for enrollment in enrollments or []:
        program_id = str(_dict_value(enrollment, "program_id")) if _dict_value(enrollment, "program_id") else ""
        if program_id:
            enrollments_by_program.setdefault(program_id, []).append(enrollment)

    submission_scores_by_program: dict[str, list[int]] = {}
    for submission in step_submissions or []:
        program_id = str(_dict_value(submission, "program_id")) if _dict_value(submission, "program_id") else ""
        score = _score_to_percent(_dict_value(submission, "ai_score"))
        if program_id and score is not None:
            submission_scores_by_program.setdefault(program_id, []).append(score)

    completed_statuses = {"completed", "accepted", "certified"}
    cancelled_statuses = {"cancelled", "archived", "locked"}
    program_rows: list[dict[str, Any]] = []
    total_program_subscribed = 0
    total_program_in_progress = 0
    total_program_completed = 0
    all_understanding_scores: list[int] = []
    for program_id, program in program_by_id.items():
        program_code = str(_dict_value(program, "code") or "")
        program_enrollments = enrollments_by_program.get(program_id, [])
        subscribed_sellers = len({
            str(_dict_value(enrollment, "seller_user_id"))
            for enrollment in program_enrollments
            if _dict_value(enrollment, "seller_user_id") and str(_dict_value(enrollment, "status") or "").lower() not in cancelled_statuses
        })
        completed_sellers = len({
            str(_dict_value(enrollment, "seller_user_id"))
            for enrollment in program_enrollments
            if _dict_value(enrollment, "seller_user_id") and (str(_dict_value(enrollment, "status") or "").lower() in completed_statuses or _dict_value(enrollment, "completed_at"))
        })
        in_progress_sellers = len({
            str(_dict_value(enrollment, "seller_user_id"))
            for enrollment in program_enrollments
            if _dict_value(enrollment, "seller_user_id")
            and str(_dict_value(enrollment, "status") or "").lower() not in completed_statuses
            and str(_dict_value(enrollment, "status") or "").lower() not in cancelled_statuses
        })
        understanding_scores: list[int] = []
        for enrollment in program_enrollments:
            score = _score_to_percent(_dict_value(enrollment, "average_score"))
            if score is not None:
                understanding_scores.append(score)
        understanding_scores.extend(submission_scores_by_program.get(program_id, []))
        all_understanding_scores.extend(understanding_scores)
        average_understanding = int(round(sum(understanding_scores) / len(understanding_scores))) if understanding_scores else None
        total_program_subscribed += subscribed_sellers
        total_program_in_progress += in_progress_sellers
        total_program_completed += completed_sellers
        attention_level = "low"
        if subscribed_sellers and completed_sellers == 0 and in_progress_sellers == 0:
            attention_level = "high"
        elif subscribed_sellers and average_understanding is not None and average_understanding < 70:
            attention_level = "medium"
        elif subscribed_sellers and completed_sellers == 0:
            attention_level = "medium"
        program_rows.append(
            {
                "program_id": program_id,
                "code": program_code,
                "title": _dict_value(program, "title"),
                "status": _dict_value(program, "status"),
                "published_materials": material_count_by_program.get(program_code, 0),
                "subscribed_sellers": subscribed_sellers,
                "in_progress_sellers": in_progress_sellers,
                "completed_sellers": completed_sellers,
                "average_understanding_percent": average_understanding,
                "attention_level": attention_level,
                "manager_action": "Проверить назначение и запустить первый урок" if attention_level == "high" else "Контролировать прохождение и ответы" if attention_level == "medium" else "Следить за динамикой программы",
            }
        )
    program_rows.sort(key=lambda item: (-int(item.get("subscribed_sellers") or 0), str(item.get("title") or "")))
    average_understanding_percent = int(round(sum(all_understanding_scores) / len(all_understanding_scores))) if all_understanding_scores else None

    return {
        "summary": {
            "published_materials": len(published_materials),
            "published_slides": sum(len(items) for items in published_slides_by_material.values()),
            "active_learners": active_learners,
            "completed_material_instances": total_completed_instances,
            "blocked_materials": blocked_materials,
            "average_completion_percent": int(round(sum(item["completion_percent"] for item in material_rows) / len(material_rows))) if material_rows else 0,
            "program_subscribed_sellers": total_program_subscribed,
            "program_in_progress_sellers": total_program_in_progress,
            "program_completed_sellers": total_program_completed,
            "average_understanding_percent": average_understanding_percent,
        },
        "programs": program_rows,
        "materials": material_rows,
        "recommendations": recommendations,
    }


def build_unlocked_step_materials_payload(
    *,
    steps: list[Any],
    step_material_links: list[Any],
    materials: list[Any],
    step_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    progress = step_progress or {}
    material_by_id = {str(_dict_value(item, "id")): item for item in materials or []}
    links_by_step: dict[str, list[Any]] = {}
    for link in step_material_links or []:
        links_by_step.setdefault(str(_dict_value(link, "step_id")), []).append(link)

    step_payloads: list[dict[str, Any]] = []
    current_step: dict[str, Any] | None = None
    unlocked_materials = 0
    for step in sorted(steps or [], key=lambda item: int(_dict_value(item, "order_index", 100) or 100)):
        step_id = str(_dict_value(step, "id"))
        status = _step_status(step_id, progress)
        is_unlocked = status not in {"locked", "blocked"}
        linked_materials: list[dict[str, Any]] = []
        if is_unlocked:
            for link in sorted(links_by_step.get(step_id, []), key=lambda item: int(_dict_value(item, "order_index", 100) or 100)):
                material = material_by_id.get(str(_dict_value(link, "material_id")))
                if not material or normalize_training_material_status(_dict_value(material, "status")) != "published":
                    continue
                linked_materials.append(build_step_material_link_payload(link, material=material, include_internal=False))
        step_item = {
            "id": step_id,
            "title": _dict_value(step, "title"),
            "status": status,
            "is_unlocked": is_unlocked,
            "locked_reason": None if is_unlocked else "complete_previous_step",
            "materials": linked_materials,
        }
        unlocked_materials += len(linked_materials)
        if is_unlocked and current_step is None and status not in {"accepted", "completed"}:
            current_step = step_item
        step_payloads.append(step_item)
    return {
        "summary": {"steps": len(step_payloads), "unlocked_materials": unlocked_materials},
        "current_step": current_step,
        "steps": step_payloads,
    }


def build_training_material_library_payload(materials: list[Any], *, seller_view: bool = False) -> dict[str, Any]:
    visible = [item for item in materials if not seller_view or normalize_training_material_status(_dict_value(item, "status")) == "published"]
    material_payloads = [build_training_material_payload(item, include_internal=not seller_view) for item in visible]
    material_payloads.sort(key=lambda item: (item.get("topic") or "Общее", int(item.get("order_index") or 100), item.get("title") or ""))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in material_payloads:
        grouped.setdefault(item.get("topic") or "Общее", []).append(item)
    topics = [{"topic": topic, "count": len(items), "materials": items} for topic, items in sorted(grouped.items(), key=lambda pair: pair[0])]
    return {
        "summary": {"total_materials": len(material_payloads), "topic_count": len(topics)},
        "topics": topics,
        "materials": material_payloads,
    }


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    text = content or ""
    if not text.lstrip().startswith("---"):
        return {}, text
    stripped = text.lstrip()
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, text
    meta: dict[str, Any] = {}
    for raw_line in lines[1:end_index]:
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            meta[key] = value
    body = "\n".join(lines[end_index + 1 :]).strip()
    return meta, body


def _split_csv_like(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]


def _title_from_markdown_or_filename(*, filename: str | None, markdown: str) -> str:
    for line in (markdown or "").splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()
    stem = PurePosixPath((filename or "material.md").replace("\\", "/")).stem
    return stem.replace("-", " ").replace("_", " ").strip().title() or "Учебный материал"


def _decode_import_file_content(file_item: dict[str, Any]) -> bytes:
    if file_item.get("content_base64"):
        data = str(file_item.get("content_base64") or "")
        if "," in data and data.strip().lower().startswith("data:"):
            data = data.split(",", 1)[1]
        return base64.b64decode(data)
    content = file_item.get("content")
    if content is None:
        return b""
    return str(content).encode("utf-8")


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml_data = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_data)
    paragraphs: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for paragraph in root.iter(f"{namespace}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def extract_training_docx_visual_assets(data: bytes, *, filename: str | None = None, max_assets: int = 24, max_inline_bytes: int = 2 * 1024 * 1024) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    filename_stem = PurePosixPath(str(filename or "training-material.docx")).stem or "training-material"
    mime_by_extension = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            media_files = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
            for image_index, media_name in enumerate(media_files, start=1):
                if len(assets) >= max_assets:
                    break
                extension = PurePosixPath(media_name).suffix.lower().lstrip(".") or "png"
                if extension not in mime_by_extension:
                    continue
                image_bytes = archive.read(media_name)
                if not image_bytes:
                    continue
                digest = hashlib.sha256(image_bytes).hexdigest()
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)
                width = None
                height = None
                try:
                    from PIL import Image  # type: ignore

                    with Image.open(io.BytesIO(image_bytes)) as image:
                        width, height = image.size
                except Exception:
                    pass
                asset: dict[str, Any] = {
                    "asset_id": f"docx-image-{digest[:12]}",
                    "filename": f"{filename_stem}-image-{image_index}.{extension}",
                    "mime_type": mime_by_extension.get(extension) or "image/png",
                    "extension": extension,
                    "page": None,
                    "image_index": image_index,
                    "width": width,
                    "height": height,
                    "size_bytes": len(image_bytes),
                    "sha256": digest,
                    "status": "pending_review",
                    "source": "docx_embedded_image",
                    "admin_only": True,
                    "storage": "extraction_metadata",
                    "has_content": False,
                    "review_note": "Изображение извлечено из DOCX и требует проверки руководителя.",
                }
                if len(image_bytes) <= max_inline_bytes:
                    asset["content_base64"] = base64.b64encode(image_bytes).decode("ascii")
                    asset["has_content"] = True
                assets.append(asset)
    except Exception:
        return assets
    return assets


def _extract_pdf_text(data: bytes) -> str:
    extraction_attempts: list[str] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages:
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    parts.append(page_text)
            text = "\n\n".join(parts)
        if text and not _looks_like_pdf_binary_garbage(text):
            return text
        extraction_attempts.append("pdfplumber_garbage_or_empty")
    except Exception as error:
        extraction_attempts.append(f"pdfplumber_failed:{str(error)[:80]}")

    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if page_text:
                parts.append(page_text)
        text = "\n\n".join(parts)
        if text and not _looks_like_pdf_binary_garbage(text):
            return text
        extraction_attempts.append("pypdf2_garbage_or_empty")
    except Exception as error:
        extraction_attempts.append(f"pypdf2_failed:{str(error)[:80]}")

    try:
        import fitz  # type: ignore

        with fitz.open(stream=data, filetype="pdf") as document:
            parts: list[str] = []
            for page in document:
                for mode in ("text", "blocks"):
                    try:
                        if mode == "blocks":
                            blocks = page.get_text("blocks") or []
                            page_text = "\n".join(str(block[4]).strip() for block in blocks if len(block) > 4 and str(block[4]).strip())
                        else:
                            page_text = page.get_text("text").strip()
                    except Exception:
                        page_text = ""
                    if page_text:
                        parts.append(page_text)
                        break
            text = "\n\n".join(part.strip() for part in parts if part.strip())
            if text and not _looks_like_pdf_binary_garbage(text):
                return text
            extraction_attempts.append("pymupdf_text_garbage_or_empty")
    except Exception as error:
        extraction_attempts.append(f"pymupdf_failed:{str(error)[:80]}")

    try:
        import pymupdf4llm  # type: ignore

        markdown = str(pymupdf4llm.to_markdown(io.BytesIO(data)) or "").strip()
        if markdown and not _looks_like_pdf_binary_garbage(markdown):
            return markdown
        extraction_attempts.append("pymupdf4llm_garbage_or_empty")
    except Exception as error:
        extraction_attempts.append(f"pymupdf4llm_failed:{str(error)[:80]}")

    return ""


def _looks_like_pdf_binary_garbage(text: str | None) -> bool:
    normalized = " ".join((text or "").split())
    if not normalized:
        return False
    lower = normalized.lower()
    pdf_tokens = [
        "endstream",
        "endobj",
        "stream",
        "fontdescriptor",
        "/font",
        "/filter",
        "/length",
        "xref",
        "trailer",
        "startxref",
    ]
    token_hits = sum(lower.count(token) for token in pdf_tokens)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", normalized)
    cyrillic_words = re.findall(r"[А-Яа-яЁё]{2,}", normalized)
    replacement_chars = normalized.count("\ufffd")
    controlish = len(re.findall(r"[^\wА-Яа-яЁё\s.,:;!?()\-/№«»\"'₽%]", normalized))
    if token_hits >= 2:
        return True
    if token_hits >= 1 and len(cyrillic_words) < 10:
        return True
    if replacement_chars >= 3:
        return True
    if len(normalized) > 120 and words and controlish / max(len(normalized), 1) > 0.08 and len(cyrillic_words) < 20:
        return True
    return False


def _normalize_import_text_to_markdown(*, filename: str, text: str) -> str:
    cleaned = "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return ""
    first_line = next((line.strip() for line in cleaned.splitlines() if line.strip()), "")
    if first_line.startswith("#"):
        return cleaned
    title = first_line if first_line and len(first_line) <= 120 else _title_from_markdown_or_filename(filename=filename, markdown=cleaned)
    return f"# {title}\n\n{cleaned}"


def build_training_document_extraction_diagnostics(*, filename: str | None, extracted_text: str | None, pages: int | None = None, extractor: str | None = None) -> dict[str, Any]:
    filename_value = str(filename or "")
    suffix = PurePosixPath(filename_value).suffix.lower().lstrip(".")
    normalized_text = " ".join((extracted_text or "").split())
    chars = len(normalized_text)
    words = len([part for part in normalized_text.split(" ") if part])
    warnings: list[str] = []
    ocr_required = False
    if suffix == "pdf" and _looks_like_pdf_binary_garbage(extracted_text):
        warnings.extend(["pdf_binary_garbage_detected", "ocr_required"])
        ocr_required = True
        quality = "needs_ocr"
    elif suffix == "pdf" and chars < 40:
        warnings.append("ocr_required")
        ocr_required = True
        quality = "needs_ocr"
    elif chars < 40:
        warnings.append("very_short_text")
        quality = "low"
    elif chars < 140:
        warnings.append("short_text_review_needed")
        quality = "low"
    elif chars < 500:
        quality = "medium"
    else:
        quality = "ok"
    if suffix == "doc":
        warnings.append("legacy_doc_fallback")
        if quality == "ok":
            quality = "medium"
    manager_note = "Качество извлечения хорошее. Достаточно методической проверки перед публикацией."
    if ocr_required:
        manager_note = "Проверьте качество извлечения: файл похож на скан, PDF без текстового слоя или содержит служебные PDF-объекты вместо текста. Нужен OCR/ручная проверка перед созданием урока."
    elif warnings:
        manager_note = "Проверьте качество извлечения: текст короткий или получен fallback-методом. Перед публикацией нужна редактура руководителя."
    return {
        "filename": filename_value,
        "extension": suffix,
        "extractor": extractor or ("pymupdf" if suffix == "pdf" else "builtin"),
        "quality": quality,
        "ocr_required": ocr_required,
        "warnings": warnings,
        "text_chars": chars,
        "word_count": words,
        "pages": pages,
        "manager_note": manager_note,
    }


def parse_training_material_document_import(
    *,
    filename: str | None,
    content: str | None = None,
    content_base64: str | None = None,
    mime_type: str | None = None,
    default_topic: str = "Общее",
    default_category: str = "Импорт документов",
    default_status: str = "draft",
) -> dict[str, Any]:
    filename_value = str(filename or "training-material.txt")
    suffix = PurePosixPath(filename_value).suffix.lower().lstrip(".")
    file_item = {"filename": filename_value, "content": content, "content_base64": content_base64}
    data = _decode_import_file_content(file_item)
    visual_assets: list[dict[str, Any]] = []
    if suffix in {"md", "markdown"}:
        extracted = content or _decode_text_bytes(data)
        material = parse_training_material_markdown_import(filename=filename_value, content=extracted, default_topic=default_topic, default_category=default_category, default_status=default_status)
    else:
        if suffix in {"txt", "text"}:
            extracted = content if content is not None else _decode_text_bytes(data)
        elif suffix == "docx":
            extracted = _extract_docx_text(data)
            visual_assets = extract_training_docx_visual_assets(data, filename=filename_value)
        elif suffix == "doc":
            extracted = _decode_text_bytes(data)
        elif suffix == "pdf":
            extracted = _extract_pdf_text(data)
            if _looks_like_pdf_binary_garbage(extracted):
                extracted = ""
            visual_assets = extract_training_pdf_visual_assets(data, filename=filename_value)
        else:
            raise ValueError("unsupported_format")
        markdown = _normalize_import_text_to_markdown(filename=filename_value, text=extracted or "")
        if not markdown and suffix == "pdf":
            title = _title_from_markdown_or_filename(filename=filename_value, markdown="")
            markdown = f"# {title}\n\nТекст не извлечен автоматически. Вероятно, это сканированный PDF: нужен OCR или ручная вставка текста перед публикацией."
        material = parse_training_material_markdown_import(filename=filename_value, content=markdown, default_topic=default_topic, default_category=default_category, default_status=default_status)
        material["source_type"] = f"{suffix}_import"
    extraction = build_training_document_extraction_diagnostics(filename=filename_value, extracted_text=extracted, extractor="pdf_text_pipeline" if suffix == "pdf" else "builtin")
    source_file: dict[str, Any] = {
        "filename": filename_value,
        "mime_type": mime_type,
        "extension": suffix,
        "size_bytes": len(data),
        "storage": "extraction_metadata",
    }
    if data and len(data) <= 8 * 1024 * 1024:
        source_file["content_base64"] = base64.b64encode(data).decode("ascii")
        source_file["has_content"] = True
    else:
        source_file["has_content"] = False
        if data:
            extraction.setdefault("warnings", []).append("source_file_too_large_for_inline_storage")
    extraction["source_file"] = source_file
    if visual_assets:
        extraction["visual_assets"] = visual_assets
        extraction["visual_assets_summary"] = {
            "total": len(visual_assets),
            "pending_review": len([asset for asset in visual_assets if asset.get("status") == "pending_review"]),
            "approved": 0,
            "rejected": 0,
            "attached": 0,
        }
        extraction.setdefault("warnings", []).append("visual_assets_pending_review")
    material["extraction"] = extraction
    material["extraction_metadata"] = extraction
    material["source_filename"] = filename_value
    material["internal_notes"] = "\n".join(
        part
        for part in [
            material.get("internal_notes"),
            f"Исходный файл: {filename_value}. Автоматически извлечен текст; перед публикацией нужна проверка руководителя.",
            extraction.get("manager_note") if extraction.get("warnings") else None,
        ]
        if part
    )
    return material


def parse_training_material_markdown_import(
    *,
    filename: str | None,
    content: str,
    default_topic: str = "Общее",
    default_category: str = "Библиотека GLAME",
    default_status: str = "draft",
) -> dict[str, Any]:
    meta, body = _split_frontmatter(content or "")
    markdown = body.strip() if body.strip() else (content or "").strip()
    title = meta.get("title") or _title_from_markdown_or_filename(filename=filename, markdown=markdown)
    return {
        "title": str(title).strip(),
        "topic": str(meta.get("topic") or default_topic or "Общее").strip(),
        "category": str(meta.get("category") or default_category or "Библиотека GLAME").strip(),
        "description": meta.get("description"),
        "markdown_content": markdown,
        "status": normalize_training_material_status(str(meta.get("status") or default_status or "draft").strip()),
        "tags": _split_csv_like(meta.get("tags")),
        "source_type": str(meta.get("source_type") or "md_import"),
        "program_code": meta.get("program_code"),
        "competencies": _split_csv_like(meta.get("competencies")),
        "internal_notes": meta.get("internal_notes"),
        "order_index": int(meta.get("order_index") or 100),
        "source_filename": filename,
    }


def enrich_training_material_import_metadata(material: dict[str, Any], *, default_program_code: str | None = None) -> dict[str, Any]:
    enriched = dict(material)
    search_text = " ".join(
        str(part or "")
        for part in [
            enriched.get("title"),
            enriched.get("topic"),
            enriched.get("category"),
            enriched.get("markdown_content"),
            " ".join(str(tag) for tag in enriched.get("tags") or []),
        ]
    ).lower()
    program_code = enriched.get("program_code") or default_program_code
    topic = enriched.get("topic") or "Общее"
    category = enriched.get("category") or "Импорт документов"
    category_is_generic = str(category or "").strip().lower() in {"", "импорт документов", "библиотека glame"}
    tags = list(enriched.get("tags") or [])
    competencies = list(enriched.get("competencies") or [])

    if program_code == "trainee_base":
        category = "Программа стажера GLAME"
        trainee_topic_rules = [
            ("База продаж: KPI и показатели", ["kpi", "показател", "выручк", "средняя стоимость", "длина чека", "конверси", "план"]),
            ("База продаж: клиентские сервисы", ["долями", "лояльност", "клуб стильных", "бонус", "оплат", "сертификат", "возврат"]),
            ("База продаж: сервис и стандарты", ["стандарт", "ско", "сервис", "первый контакт", "коммуникац", "приветств", "потребност", "возражен"]),
            ("База ассортимента: украшения и материалы", ["виды украшений", "металл", "покрыти", "камн", "застеж", "размер кольца", "уход"]),
            ("База GLAME: бренд и концепция", ["бренд", "концепц", "мисси", "ценност", "стиль внутри", "о компании", "glame"]),
        ]
        matched_topic = next((label for label, tokens in trainee_topic_rules if any(token in search_text for token in tokens)), None)
        topic = matched_topic or "База стажера GLAME"
        if topic == "База GLAME: бренд и концепция":
            tags.extend(["бренд", "ценности", "концепция"])
            competencies.extend(["знание бренда GLAME", "ценности GLAME"])
        elif topic == "База продаж: сервис и стандарты":
            tags.extend(["сервис", "коммуникация", "стандарты"])
            competencies.extend(["первый контакт", "стандарты GLAME"])
        elif topic == "База продаж: клиентские сервисы":
            tags.extend(["сервис", "оплата", "лояльность"])
            competencies.extend(["клиентские сервисы", "стандарты GLAME"])
        elif topic == "База продаж: KPI и показатели":
            tags.extend(["kpi", "продажи", "показатели"])
            competencies.extend(["понимание KPI", "продажи"])
        elif topic == "База ассортимента: украшения и материалы":
            tags.extend(["ассортимент", "украшения", "материалы"])
            competencies.extend(["знание ассортимента", "базовые знания украшений"])
        else:
            tags.extend(["стажировка", "база glame"])
            competencies.extend(["база стажера"])
    else:
        if any(token in search_text for token in ["бренд", "glame", "ценност", "стандарт", "сервис", "первый контакт", "коммуникац"]):
            topic = "Бренд и сервис GLAME"
            if category_is_generic:
                category = "Сервис GLAME"
            tags.extend(["бренд", "сервис", "коммуникация"])
            competencies.extend(["первый контакт", "стандарты GLAME"])
        if any(token in search_text for token in ["стил", "образ", "форма лица", "тренд", "ss26", "украшен", "dna", "classic", "romantic", "dramatic", "natural"]):
            topic = "Стилистический подбор" if "тренд" not in search_text and "ss26" not in search_text else "Тренды и стилизация"
            if category_is_generic:
                category = "GLAME Stylist Academy"
            tags.extend(["стилизация", "украшения", "образ"])
            competencies.extend(["стилистический подбор", "эффект украшения"])
            if not program_code:
                program_code = "stylist_academy"
        if "первый контакт" in search_text:
            tags.append("первый контакт")
            competencies.append("первый контакт")

    extraction = dict(enriched.get("extraction_metadata") or enriched.get("extraction") or {})
    auto_recognized = {
        "program_code": program_code,
        "topic": topic,
        "category": category,
        "tags": sorted(set(str(tag).strip() for tag in tags if str(tag).strip())),
        "competencies": sorted(set(str(item).strip() for item in competencies if str(item).strip())),
    }
    extraction["auto_recognized"] = auto_recognized
    enriched["program_code"] = program_code
    enriched["topic"] = topic
    enriched["category"] = category
    enriched["tags"] = auto_recognized["tags"]
    enriched["competencies"] = auto_recognized["competencies"]
    enriched["extraction"] = extraction
    enriched["extraction_metadata"] = extraction
    note = "Агент автоматически распознал исходник и заполнил программу, тему, категорию, теги и компетенции. Проверьте draft перед публикацией."
    enriched["internal_notes"] = "\n".join(part for part in [enriched.get("internal_notes"), note] if part)
    return enriched


def build_training_material_bulk_import_payload(
    *,
    files: list[dict[str, Any]],
    default_topic: str = "Общее",
    default_category: str = "Библиотека GLAME",
    default_status: str = "draft",
    default_program_code: str | None = None,
) -> dict[str, Any]:
    materials: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for file_item in files or []:
        filename = str(file_item.get("filename") or "material.md")
        suffix = PurePosixPath(filename).suffix.lower().lstrip(".")
        if suffix not in {"md", "markdown", "txt", "text", "pdf", "doc", "docx"}:
            skipped.append({"filename": filename, "reason": "unsupported_format"})
            continue
        has_text = bool(str(file_item.get("content") or "").strip())
        has_binary = bool(str(file_item.get("content_base64") or "").strip())
        if not has_text and not has_binary:
            skipped.append({"filename": filename, "reason": "empty_file"})
            continue
        try:
            material = parse_training_material_document_import(
                filename=filename,
                content=file_item.get("content"),
                content_base64=file_item.get("content_base64"),
                mime_type=file_item.get("mime_type"),
                default_topic=default_topic,
                default_category=default_category,
                default_status=default_status,
            )
        except ValueError as error:
            skipped.append({"filename": filename, "reason": str(error) or "unsupported_format"})
            continue
        except Exception as error:
            skipped.append({"filename": filename, "reason": "extract_failed", "detail": str(error)[:180]})
            continue
        if default_program_code and not material.get("program_code"):
            material["program_code"] = default_program_code
        material = enrich_training_material_import_metadata(material, default_program_code=default_program_code)
        if not str(material.get("markdown_content") or "").strip():
            skipped.append({"filename": filename, "reason": "empty_file"})
            continue
        title_key = material["title"].strip().lower()
        if title_key in seen_titles:
            skipped.append({"filename": filename, "title": material["title"], "reason": "duplicate_title"})
            continue
        seen_titles.add(title_key)
        materials.append(material)
    warnings_count = sum(1 for material in materials if (material.get("extraction") or {}).get("warnings"))
    return {
        "summary": {"total_files": len(files or []), "ready_to_import": len(materials), "skipped": len(skipped), "warnings": warnings_count},
        "materials": materials,
        "skipped_files": skipped,
    }


def _material_search_text(material: dict[str, Any]) -> str:
    parts = [
        material.get("title") or "",
        material.get("topic") or "",
        material.get("category") or "",
        material.get("description") or "",
        material.get("markdown_content") or "",
        " ".join(str(tag) for tag in (material.get("tags") or [])),
        " ".join(str(item) for item in (material.get("competencies") or [])),
    ]
    return " ".join(parts).lower()


def _material_snippet(markdown: str, query: str | None, *, max_chars: int = 180) -> str:
    text = " ".join((markdown or "").split())
    if not text:
        return ""
    query_text = (query or "").strip().lower()
    if query_text:
        index = text.lower().find(query_text)
        if index >= 0:
            start = max(0, index - 50)
            end = min(len(text), index + len(query_text) + 90)
            prefix = "…" if start else ""
            suffix = "…" if end < len(text) else ""
            return f"{prefix}{text[start:end]}{suffix}"
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _material_match_score(material: dict[str, Any], *, query: str | None = None, topic: str | None = None, category: str | None = None, competency: str | None = None) -> int:
    score = 0
    search_text = _material_search_text(material)
    title_text = str(material.get("title") or "").lower()
    topic_text = str(material.get("topic") or "").lower()
    category_text = str(material.get("category") or "").lower()
    for needle, weight in ((query, 4), (competency, 5)):
        if not needle:
            continue
        needle_text = str(needle).strip().lower()
        if not needle_text:
            continue
        if needle_text in title_text:
            score += weight + 3
        elif needle_text in topic_text:
            score += weight + 2
        elif needle_text in search_text:
            score += weight
        else:
            for token in [part for part in needle_text.replace("-", " ").split() if len(part) >= 4]:
                if token in search_text:
                    score += 1
    if topic and str(topic).strip().lower() == topic_text:
        score += 3
    if category and str(category).strip().lower() == category_text:
        score += 2
    return score


def build_training_material_search_payload(
    materials: list[Any],
    *,
    query: str | None = None,
    topic: str | None = None,
    category: str | None = None,
    seller_view: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    material_payloads = [build_training_material_payload(item, include_internal=not seller_view) for item in materials]
    if seller_view:
        material_payloads = [item for item in material_payloads if item.get("status") == "published"]
    if topic:
        material_payloads = [item for item in material_payloads if (item.get("topic") or "").lower() == topic.strip().lower()]
    if category:
        material_payloads = [item for item in material_payloads if (item.get("category") or "").lower() == category.strip().lower()]

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in material_payloads:
        score = _material_match_score(item, query=query, topic=topic, category=category)
        if query and score <= 0:
            continue
        result = dict(item)
        result["match_score"] = score
        result["snippet"] = _material_snippet(result.get("markdown_content") or "", query)
        scored.append((score, result))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("topic") or "", int(pair[1].get("order_index") or 100), pair[1].get("title") or ""))
    selected = [item for _, item in scored[: max(1, int(limit or 50))]]
    return {
        "summary": {
            "total_matches": len(selected),
            "query": query or "",
            "topic": topic,
            "category": category,
            "seller_view": seller_view,
        },
        "materials": selected,
    }


def build_training_material_context_payload(
    materials: list[Any],
    *,
    query: str | None = None,
    competency: str | None = None,
    topic: str | None = None,
    max_materials: int = 3,
    max_chars: int = 1200,
) -> dict[str, Any]:
    candidates = [build_training_material_payload(item, include_internal=False) for item in materials]
    candidates = [item for item in candidates if item.get("status") == "published"]
    if topic:
        candidates = [item for item in candidates if (item.get("topic") or "").lower() == topic.strip().lower()]
    scored = []
    for item in candidates:
        score = _material_match_score(item, query=query, topic=topic, competency=competency)
        if query or competency or topic:
            if score <= 0:
                continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("topic") or "", int(pair[1].get("order_index") or 100), pair[1].get("title") or ""))
    selected = [item for _, item in scored[: max(1, int(max_materials or 3))]]

    chunks: list[str] = []
    remaining = max(120, int(max_chars or 1200))
    for item in selected:
        header = f"## {item.get('title')}\nТема: {item.get('topic')} · Категория: {item.get('category')}\n"
        body = item.get("markdown_content") or ""
        chunk = (header + body).strip()
        if len(chunk) > remaining:
            chunk = chunk[:remaining].rstrip() + "…"
        chunks.append(chunk)
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return {
        "summary": {
            "selected_materials": len(chunks),
            "query": query or "",
            "competency": competency,
            "topic": topic,
            "max_chars": max_chars,
        },
        "materials": selected[: len(chunks)],
        "context_markdown": "\n\n---\n\n".join(chunks),
    }


def build_program_structure_payload(*, program: Any, modules: list[Any], steps: list[Any], step_progress: dict[str, dict] | None = None) -> dict[str, Any]:
    progress = step_progress or {}
    sorted_modules = sorted(modules, key=lambda item: int(_dict_value(item, "order_index", 100) or 100))
    sorted_steps = sorted(steps, key=lambda item: (str(_dict_value(item, "module_id")), int(_dict_value(item, "order_index", 100) or 100)))
    completed_steps = 0
    total_steps = len(sorted_steps)
    next_step = None
    previous_required_accepted = True
    module_payloads: list[dict[str, Any]] = []

    for module in sorted_modules:
        module_id = str(_dict_value(module, "id"))
        module_steps = [step for step in sorted_steps if str(_dict_value(step, "module_id")) == module_id]
        step_payloads = []
        for step in module_steps:
            step_id = str(_dict_value(step, "id"))
            current_progress = progress.get(step_id, {})
            stored_status = current_progress.get("status")
            if stored_status:
                status = stored_status
            elif previous_required_accepted:
                status = "available"
            else:
                status = "locked"
            if status == "accepted":
                completed_steps += 1
            if next_step is None and status in {"available", "opened", "in_progress", "needs_revision"}:
                next_step = {"id": step_id, "title": _dict_value(step, "title"), "status": status}
            if _program_bool(_dict_value(step, "is_required", True)) and status != "accepted":
                previous_required_accepted = False
            step_payloads.append(
                {
                    "id": step_id,
                    "module_id": module_id,
                    "title": _dict_value(step, "title"),
                    "lesson_text": _dict_value(step, "lesson_text"),
                    "practice_text": _dict_value(step, "practice_text"),
                    "answer_template": _dict_value(step, "answer_template"),
                    "assessment_rubric": _dict_value(step, "assessment_rubric", {}) or {},
                    "competencies": _dict_value(step, "competencies", []) or [],
                    "unlock_rule": _dict_value(step, "unlock_rule", {}) or {},
                    "is_required": _program_bool(_dict_value(step, "is_required", True)),
                    "order_index": int(_dict_value(step, "order_index", 100) or 100),
                    "status": status,
                    "score": current_progress.get("score"),
                }
            )
        module_payloads.append(
            {
                "id": module_id,
                "title": _dict_value(module, "title"),
                "description": _dict_value(module, "description"),
                "order_index": int(_dict_value(module, "order_index", 100) or 100),
                "steps": step_payloads,
            }
        )

    percent = round((completed_steps / total_steps) * 100) if total_steps else 0
    return {
        "program": {
            "id": str(_dict_value(program, "id")),
            "code": _dict_value(program, "code"),
            "title": _dict_value(program, "title"),
            "description": _dict_value(program, "description"),
        },
        "modules": module_payloads,
        "progress": {"completed_steps": completed_steps, "total_steps": total_steps, "percent": percent},
        "next_step": next_step,
    }


def normalize_attestation_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    if status in ALLOWED_ATTESTATION_STATUSES:
        return status
    return "draft"


def build_current_learning_task_payload(
    *,
    programs: list[dict[str, Any]] | None = None,
    daily_focus: dict[str, Any] | None = None,
    competency_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    program_cards = programs or []
    inactive_statuses = {"locked", "archived"}
    available_programs = [program for program in program_cards if program.get("status") not in inactive_statuses]
    primary_program = next((program for program in available_programs if program.get("next_assignment")), None)
    primary_program = primary_program or (available_programs[0] if available_programs else None)
    assignment = (primary_program or {}).get("next_assignment") or {}
    progress = (primary_program or {}).get("progress") or {}
    completed_steps = int(progress.get("completed_steps") or 0)
    pending_reviews = int(progress.get("pending_reviews") or 0)
    revision_count = int(progress.get("revision_count") or 0)

    if revision_count:
        cta = "Доработать ответ"
    elif pending_reviews or (assignment.get("status") == "submitted"):
        cta = "Ожидает проверки"
    elif completed_steps:
        cta = "Продолжить обучение"
    else:
        cta = "Начать обучение"

    weakest = ((competency_profile or {}).get("weakest_competencies") or [])
    knowledge_focus = weakest[0] if weakest else None
    task_title = assignment.get("title") or (primary_program or {}).get("title") or "Открыть программу GLAME"
    program_title = (primary_program or {}).get("title") or "GLAME school"
    recommended_action = (daily_focus or {}).get("recommended_action") or "Откройте урок, выполните практику и отправьте конкретный ответ на проверку."
    micro_practice = (daily_focus or {}).get("micro_practice") or "Сформулируйте одну спокойную GLAME-фразу для клиента."

    return {
        "primary_task": {
            "program_id": (primary_program or {}).get("id"),
            "program_code": (primary_program or {}).get("code"),
            "program_title": program_title,
            "step_id": assignment.get("id"),
            "title": task_title,
            "status": assignment.get("status") or (primary_program or {}).get("status") or "available",
            "cta": cta,
            "progress": {
                "completed_steps": completed_steps,
                "total_steps": int(progress.get("total_steps") or 0),
                "percent": int(progress.get("percent") or 0),
            },
        },
        "learning_flow": ["lesson", "practice", "answer", "ai_review", "manager_review", "accepted_or_revision"],
        "seller_guidance": {
            "recommended_action": recommended_action,
            "micro_practice": micro_practice,
            "review_rule": "AI готовит предварительный разбор, финальный комментарий продавцу подтверждает руководитель.",
            "revision_rule": "Если ответ слишком общий, его мягко вернут на доработку с конкретной подсказкой.",
        },
        "knowledge_focus": knowledge_focus,
        "mentor_prompt": f"AI-наставник GLAME: помоги начать задание «{task_title}» в программе «{program_title}». Дай структуру ответа, GLAME-фразу и самопроверку перед отправкой руководителю.",
    }


def build_training_material_practice_assignment_payload(*, material: dict[str, Any] | Any | None = None, step_title: str | None = None) -> dict[str, Any]:
    material_title = _dict_value(material, "title") or step_title or "текущий методический материал GLAME"
    topic = _dict_value(material, "topic") or "текущая тема"
    return {
        "title": f"Практика по материалу: {material_title}",
        "task": (
            f"Что сделать: после изучения материала «{material_title}» найдите в магазине 5 украшений, которые подходят под тему «{topic}». "
            "Для каждого украшения коротко опишите: Style DNA, клиентскую ситуацию, с чем носить, какой эффект украшение дает образу и как предложить примерку без давления. "
            "Если в смене был подходящий клиент, примените минимум одну фразу в диалоге и запишите, что сработало."
        ),
        "try_phrase": "Можно примерить как один главный акцент — образ сразу станет собраннее, но без перегруза.",
        "answer_template": (
            "1) 5 украшений GLAME: название/описание.\n"
            "2) Для каждого: Style DNA, задача клиента, с чем носить, эффект на образ.\n"
            "3) Фраза продавца в спокойном языке GLAME.\n"
            "4) Как предложить примерку без давления.\n"
            "5) Что попробовали в смене и какой вывод сделали."
        ),
        "good_answer_example": (
            "Хороший ответ: «Крупные гладкие серьги в металле — для клиента с Classic/Dramatic настроением, когда базовой рубашке нужен один статусный акцент. "
            "Я бы сказала: “Можно примерить их как главный акцент: рубашка останется спокойной, но образ станет более собранным и современным”. "
            "Дальше предложила бы сравнить с более мягким вариантом, чтобы клиент сам почувствовал комфортный масштаб»."
        ),
        "assessment_criteria": [
            "Конкретика: указаны реальные украшения или понятные описания изделий GLAME, а не общие слова.",
            "Связь с материалом: ответ действительно применяет тему урока и не уходит в другую программу.",
            "Эффект на образ: объяснено, что украшение меняет для клиента — статус, свежесть, собранность, акцент.",
            "Язык GLAME: фразы спокойные, профессиональные, без давления, оценок внешности и “надо брать”.",
            "Практическое применение: понятно, как продавец покажет изделие, предложит примерку и сделает следующий деликатный шаг.",
            "Рефлексия: есть короткий вывод после смены — что сработало, где клиент сомневался, что улучшить.",
        ],
        "review_rule": "AI делает предварительный разбор; итоговую оценку и обратную связь продавцу подтверждает руководитель.",
    }


def build_training_mentor_session_payload(
    *,
    current_task: dict[str, Any] | None = None,
    step_materials: dict[str, Any] | None = None,
    daily_focus: dict[str, Any] | None = None,
    current_material: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = (current_task or {}).get("primary_task") or {}
    material_override = current_material or None
    current_step = (step_materials or {}).get("current_step") or None
    practice_gate = (current_step or {}).get("practice_gate") or {}
    task_status = str(task.get("status") or "").lower()
    step_id = (material_override or {}).get("step_id") or (current_step or {}).get("id") or task.get("step_id")
    program_id = (material_override or {}).get("program_id") or task.get("program_id")
    material_links = (current_step or {}).get("materials") or []
    primary_material = next((item for item in material_links if item.get("required_to_complete")), None) or (material_links[0] if material_links else None)
    blocked_materials = practice_gate.get("blocked_materials") or []
    blocked_material = blocked_materials[0] if blocked_materials else None
    material_id = (material_override or {}).get("id") or (blocked_material or {}).get("material_id") or (primary_material or {}).get("material_id")
    material_title = (material_override or {}).get("title") or (blocked_material or {}).get("title") or (primary_material or {}).get("title")
    step_title = (material_override or {}).get("step_title") or (current_step or {}).get("title") or task.get("title") or material_title or "текущий этап"
    material_progress = (material_override or {}).get("progress") or {}
    practice_assignment = build_training_material_practice_assignment_payload(material=material_override or primary_material, step_title=step_title) if (material_override or material_id) else None
    mentor_prompt_base = f"AI-наставник GLAME: мягко продолжи обучение продавца по этапу «{step_title}»."

    if task_status in {"submitted", "review_pending", "waiting_review"}:
        stage = "review"
        next_action = "wait_manager_review"
        message = "Ответ отправлен. Я сохраню фокус обучения и продолжу после проверки руководителем."
    elif task_status in {"needs_revision", "revision_requested", "revision_draft"}:
        stage = "practice"
        next_action = "revise_answer"
        message = "Ответ нужно мягко доработать. Давайте усилим конкретику, пример украшения и GLAME-фразу без давления."
    elif material_override and not bool(material_progress.get("material_completed")):
        stage = "materials"
        next_action = "continue_material"
        message = f"Сначала изучаем урок «{material_title or step_title}»: откройте слайды, просмотрите их по порядку и отметьте как изученные. Только после этого я открою закрепление и практическое задание."
    elif material_override:
        stage = "practice"
        next_action = "start_practice"
        message = f"Методический материал «{material_title or step_title}» изучен. Теперь открываю закрепление и практическое задание только по этой теме."
    elif current_step and practice_gate.get("can_start_practice"):
        stage = "practice"
        next_action = "start_practice"
        message = f"Методическая часть по этапу «{step_title}» изучена. Теперь открываю закрепление, практическое задание и форму ответа."
    elif current_step and material_id:
        stage = "materials"
        next_action = "continue_material"
        message = f"Продолжаем изучение материала «{material_title or step_title}». После обязательных слайдов я открою практическое задание."
    elif task:
        stage = "program"
        next_action = "open_program"
        message = f"Я нашел ваш текущий учебный шаг «{step_title}» и открою его как персональный маршрут."
    else:
        stage = "waiting"
        next_action = "wait_assignment"
        message = "Сейчас нет активного учебного шага. Я жду назначения материала или задания от руководителя."

    context = {
        "task_title": task.get("title"),
        "step_title": step_title if step_id else None,
        "material_title": material_title,
        "daily_focus": (daily_focus or {}).get("recommended_action"),
        "review_rule": "AI помогает и готовит черновой разбор; финальная обратная связь остается за руководителем.",
    }
    if practice_assignment:
        context["practice_assignment"] = practice_assignment
    if material_progress:
        context["material_progress"] = {
            "slides": int(material_progress.get("slides") or 0),
            "completed_slides": int(material_progress.get("completed_slides") or 0),
            "progress_percent": int(material_progress.get("progress_percent") or 0),
            "material_completed": bool(material_progress.get("material_completed")),
        }

    return {
        "stage": stage,
        "message": message,
        "next_action": next_action,
        "material_id": material_id,
        "step_id": step_id,
        "program_id": program_id,
        "mentor_prompt": f"{mentor_prompt_base} Следующее действие: {next_action}. Подскажи продавцу один конкретный шаг и самопроверку перед отправкой руководителю.",
        "context": context,
    }


SELLER_CAREER_LEVELS = [
    {"code": "trainee", "title": "Стажер", "min_score": 0},
    {"code": "junior", "title": "Junior consultant", "min_score": 55},
    {"code": "consultant", "title": "Consultant", "min_score": 70},
    {"code": "stylist", "title": "Stylist consultant", "min_score": 82},
    {"code": "senior", "title": "Senior stylist / mentor", "min_score": 90},
]


def build_seller_career_level_payload(
    *,
    competency_profile: dict[str, Any] | None = None,
    kpi_summary: dict[str, Any] | None = None,
    programs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile = competency_profile or {}
    kpi = kpi_summary or {}
    program_cards = programs or []
    completed_steps = int(profile.get("completed_steps") or 0)
    total_steps = int(profile.get("total_steps") or 0)
    learning_percent = round((completed_steps / total_steps) * 100) if total_steps else 0
    average_score = float(profile.get("average_score") or 0)
    kpi_percent = int(kpi.get("completion_percent") or kpi.get("plan_completion_percent") or 0)
    achievement_count = len(profile.get("achievements") or [])
    pending_reviews = sum(int((program.get("progress") or {}).get("pending_reviews") or 0) for program in program_cards)
    revision_count = sum(int((program.get("progress") or {}).get("revision_count") or 0) for program in program_cards)
    attestation_bonus = 10 if profile.get("attestation_ready") else 0
    knowledge_score = min(100, round((learning_percent * 0.65) + (average_score * 3.5)))
    sales_score = min(100, kpi_percent)
    quality_score = min(100, max(0, 60 + achievement_count * 10 - revision_count * 8 - pending_reviews * 2 + attestation_bonus))
    total_score = round(knowledge_score * 0.45 + sales_score * 0.35 + quality_score * 0.20)

    current_level = SELLER_CAREER_LEVELS[0]
    for level in SELLER_CAREER_LEVELS:
        if total_score >= level["min_score"]:
            current_level = level
    current_index = SELLER_CAREER_LEVELS.index(current_level)
    next_level = SELLER_CAREER_LEVELS[min(current_index + 1, len(SELLER_CAREER_LEVELS) - 1)]
    requirements: list[str] = []
    if learning_percent < 60:
        requirements.append("закрыть больше учебных этапов и закрепить знания GLAME")
    if average_score < 8:
        requirements.append("поднять средний балл ответов до 8/10 через конкретику и язык GLAME")
    if kpi_percent < 80:
        requirements.append("улучшить реальные продажи и выполнение KPI без давления на клиента")
    if revision_count:
        requirements.append("доработать слабые ответы и закрыть замечания наставника")
    if pending_reviews:
        requirements.append("дождаться проверки руководителем отправленных ответов")
    if not requirements:
        requirements.append("пройти аттестацию и подтвердить уровень руководителем")

    return {
        "current_level": {"code": current_level["code"], "title": current_level["title"], "score": total_score},
        "next_level": {"code": next_level["code"], "title": next_level["title"], "min_score": next_level["min_score"]},
        "level_track": SELLER_CAREER_LEVELS,
        "score_breakdown": {
            "знания": knowledge_score,
            "реальные продажи": sales_score,
            "качество сервиса и достижения": quality_score,
        },
        "requirements_to_next_level": requirements,
        "salary_policy": {
            "status": "pending_management_approval",
            "description": "Связь уровня с зарплатой и бонусами будет применяться только после утверждения правил руководством GLAME.",
        },
        "mentor_rule": "AI-наставник ведет продавца ежедневно: обучение, практика, ответы, продажи, рефлексия и рост уровня.",
    }


def _match_kpi_for_seller_profile(seller: dict[str, Any] | None, kpi_sellers: list[dict[str, Any]]) -> dict[str, Any]:
    seller = seller or {}
    seller_name = _training_kpi_normalize_name(seller.get("full_name") or seller.get("name") or seller.get("email"))
    seller_external = str(seller.get("seller_external_id") or seller.get("external_id") or "").strip()
    for row in kpi_sellers or []:
        row_external = str(row.get("seller_external_id") or row.get("external_id") or "").strip()
        if seller_external and row_external and seller_external == row_external:
            return row
    for row in kpi_sellers or []:
        row_name = _training_kpi_normalize_name(row.get("seller_name") or row.get("name"))
        if seller_name and row_name and (seller_name == row_name or seller_name in row_name or row_name in seller_name):
            return row
    return {}


def build_team_career_levels_payload(
    *,
    seller_profiles: list[dict[str, Any]] | None = None,
    kpi_sellers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    seller_rows: list[dict[str, Any]] = []
    level_distribution: dict[str, int] = {}
    total_score = 0
    attention_count = 0
    for item in seller_profiles or []:
        seller = item.get("seller") or {}
        profile = item.get("profile") or {}
        kpi = _match_kpi_for_seller_profile(seller, kpi_sellers or [])
        career_level = build_seller_career_level_payload(competency_profile=profile, kpi_summary=kpi, programs=item.get("programs") or [])
        level_title = career_level["current_level"]["title"]
        level_distribution[level_title] = level_distribution.get(level_title, 0) + 1
        score = int(career_level["current_level"].get("score") or 0)
        total_score += score
        requirements = career_level.get("requirements_to_next_level") or []
        if score < 70 or requirements:
            attention_count += 1
        if profile.get("attestation_ready"):
            manager_next_action = "Назначить аттестацию и подтвердить уровень руководителем."
        elif requirements:
            manager_next_action = f"Закрепить следующий шаг: {requirements[0]}."
        else:
            manager_next_action = "Поддерживать уровень через ежедневные задания и coaching по сменам."
        seller_rows.append(
            {
                "seller": seller,
                "profile": profile,
                "kpi": kpi,
                "career_level": career_level,
                "manager_next_action": manager_next_action,
            }
        )
    seller_rows.sort(key=lambda row: int((row.get("career_level") or {}).get("current_level", {}).get("score") or 0))
    total_sellers = len(seller_rows)
    return {
        "summary": {
            "total_sellers": total_sellers,
            "average_score": round(total_score / total_sellers) if total_sellers else 0,
            "attention_count": attention_count,
            "level_distribution": level_distribution,
        },
        "level_track": SELLER_CAREER_LEVELS,
        "salary_policy": {
            "status": "pending_management_approval",
            "description": "Связь карьерного уровня с зарплатой и бонусами требует утверждения руководством GLAME; суммы и формулы здесь намеренно не задаются.",
        },
        "sellers": seller_rows,
    }


def build_attestation_payload(*, attestation: Any, competency_profile: dict[str, Any] | None = None, include_internal: bool = False) -> dict[str, Any]:
    profile = competency_profile or {}
    status = normalize_attestation_status(_dict_value(attestation, "status", None))
    payload = {
        "id": str(_dict_value(attestation, "id")),
        "program_id": str(_dict_value(attestation, "program_id")),
        "seller_user_id": str(_dict_value(attestation, "seller_user_id")),
        "attestation_type": _dict_value(attestation, "attestation_type", "trainee_final"),
        "status": status,
        "eligible": bool(profile.get("attestation_ready")),
        "recommended_level": profile.get("level"),
        "ai_score": _dict_value(attestation, "ai_score"),
        "manager_decision": _dict_value(attestation, "manager_decision"),
        "manager_feedback": _dict_value(attestation, "manager_feedback"),
        "certified_level": _dict_value(attestation, "certified_level"),
        "created_at": _dict_value(attestation, "created_at"),
        "submitted_at": _dict_value(attestation, "submitted_at"),
        "reviewed_at": _dict_value(attestation, "reviewed_at"),
    }
    if include_internal:
        payload["ai_evaluation"] = _dict_value(attestation, "ai_evaluation", {}) or {}
        payload["competency_snapshot"] = _dict_value(attestation, "competency_snapshot", profile) or profile
    return payload


def normalize_mentor_message_role(value: str | None) -> str:
    role = (value or "").strip().lower()
    if role in ALLOWED_MENTOR_MESSAGE_ROLES:
        return role
    return "user"


def build_mentor_reply(*, question: str, context: dict[str, Any] | None = None, competency_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_question = (question or "").strip()
    ctx = context or {}
    profile = competency_profile or {}
    lower_question = clean_question.lower()
    weakest = profile.get("weakest_competencies") or []
    weakest_labels = [item.get("label") or item.get("code") for item in weakest if isinstance(item, dict)]
    focus_tags = [tag for tag in [ctx.get("step_title"), ctx.get("program_title"), *weakest_labels] if tag]
    asks_for_final_grade = any(term in lower_question for term in ["сдаю", "сдала", "сдал", "оцен", "аттестаци", "зачёт", "зачет"])

    response_parts = []
    if ctx.get("step_title"):
        response_parts.append(f"Разберём в контексте этапа «{ctx['step_title']}».")
    else:
        response_parts.append("Разберём как учебную тренировку GLAME-консультанта.")
    response_parts.append("Я могу помочь усилить формулировку: назовите конкретное украшение, опишите эффект на образ и добавьте спокойную клиентскую фразу без давления.")
    if weakest_labels:
        response_parts.append(f"Особое внимание сейчас: {', '.join(weakest_labels[:2])}.")
    if asks_for_final_grade:
        response_parts.append("Финальную оценку, аттестацию и обратную связь подтверждает руководитель; я даю только учебную подсказку и черновую самопроверку.")
    response_parts.append("Попробуйте ответить по формуле: изделие → какой характер/мягкость/собранность даёт образу → с чем носить → фраза клиенту.")

    return {
        "sender_role": "mentor",
        "question_text": clean_question,
        "response_text": " ".join(response_parts),
        "context": ctx,
        "focus_tags": focus_tags[:6],
        "requires_manager_review": asks_for_final_grade,
        "risk_flags": ["needs_manager_review"] if asks_for_final_grade else [],
    }


def build_mentor_reply_with_library_context(
    *,
    question: str,
    context: dict[str, Any] | None = None,
    competency_profile: dict[str, Any] | None = None,
    library_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reply = build_mentor_reply(question=question, context=context, competency_profile=competency_profile)
    lib = library_context or {}
    source_materials = [
        {
            "id": material.get("id"),
            "title": material.get("title"),
            "topic": material.get("topic"),
            "category": material.get("category"),
        }
        for material in (lib.get("materials") or [])
        if isinstance(material, dict)
    ]
    if source_materials:
        source_titles = ", ".join(material.get("title") or "Материал" for material in source_materials[:3])
        reply["response_text"] = f"{reply['response_text']} Источник библиотеки GLAME: {source_titles}. Опираться нужно только на опубликованные учебные материалы; если нужна оценка ответа, её подтвердит руководитель."
        source_topics = [material.get("topic") for material in source_materials if material.get("topic")]
        reply["focus_tags"] = [*reply.get("focus_tags", []), *source_topics[:3]][:8]
    reply["source_materials"] = source_materials
    reply["library_context_markdown"] = lib.get("context_markdown") or ""
    merged_context = dict(reply.get("context") or {})
    merged_context["library_context"] = {
        "selected_materials": (lib.get("summary") or {}).get("selected_materials", len(source_materials)),
        "source_materials": source_materials,
    }
    reply["context"] = merged_context
    return reply



def build_mentor_message_payload(message: Any, *, include_internal: bool = False) -> dict[str, Any]:
    role = normalize_mentor_message_role(_dict_value(message, "sender_role", None))
    payload = {
        "id": str(_dict_value(message, "id")),
        "seller_user_id": str(_dict_value(message, "seller_user_id")),
        "program_id": str(_dict_value(message, "program_id")) if _dict_value(message, "program_id") else None,
        "step_id": str(_dict_value(message, "step_id")) if _dict_value(message, "step_id") else None,
        "sender_role": role,
        "question_text": _dict_value(message, "question_text"),
        "response_text": _dict_value(message, "response_text"),
        "context": _dict_value(message, "context", {}) or {},
        "created_at": _dict_value(message, "created_at"),
    }
    if include_internal:
        payload["risk_flags"] = _dict_value(message, "risk_flags", []) or []
    return payload


def _increment_counter(counter: dict[str, dict[str, Any]], key: str, *, label: str | None = None, field: str = "count") -> None:
    if not key:
        return
    item = counter.setdefault(key, {"label": label or key, field: 0})
    item[field] = item.get(field, 0) + 1


def _training_kpi_normalize_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("ё", "е").split())


def _safe_round_average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _seller_identity_values(user: Any) -> dict[str, Any]:
    preferences = _dict_value(user, "preferences", {}) or {}
    if not isinstance(preferences, dict):
        preferences = {}
    return {
        "id": str(_dict_value(user, "id")),
        "full_name": _dict_value(user, "full_name") or _dict_value(user, "name"),
        "email": _dict_value(user, "email"),
        "role": _dict_value(user, "role"),
        "preferences": preferences,
        "external_ids": [
            str(preferences.get("seller_external_id") or "").strip(),
            str(preferences.get("onec_seller_id") or "").strip(),
            str(preferences.get("employee_external_id") or "").strip(),
        ],
        "names": [
            _dict_value(user, "full_name"),
            _dict_value(user, "email"),
            preferences.get("seller_name"),
            preferences.get("staff_name"),
            preferences.get("onec_seller_name"),
        ],
    }


def build_seller_training_account_preferences_update(
    *,
    current_preferences: dict[str, Any] | None,
    seller_external_id: str,
    seller_name: str | None = None,
    store_name: str | None = None,
    manager_user_id: str | None = None,
) -> dict[str, Any]:
    preferences = dict(current_preferences or {}) if isinstance(current_preferences, dict) else {}
    previous_external_id = str(preferences.get("seller_external_id") or preferences.get("onec_seller_id") or "").strip() or None
    now = datetime.now(timezone.utc).isoformat()
    external_id = str(seller_external_id or "").strip()
    preferences.update({
        "seller_external_id": external_id,
        "onec_seller_id": external_id,
    })
    if seller_name:
        preferences["seller_name"] = seller_name
        preferences["onec_seller_name"] = seller_name
    if store_name:
        preferences["seller_store_name"] = store_name
    preferences["training_account_mapping"] = {
        "mapped_at": now,
        "mapped_by_user_id": str(manager_user_id) if manager_user_id else None,
        "previous_seller_external_id": previous_external_id,
        "seller_external_id": external_id,
        "seller_name": seller_name,
        "store_name": store_name,
        "source": "manual_admin_mapping",
    }
    return preferences


def build_seller_training_account_matching_payload(*, kpi_sellers: list[dict[str, Any]], users: list[Any]) -> dict[str, Any]:
    user_identities = [_seller_identity_values(user) for user in users]
    matches: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    matched_user_ids: set[str] = set()
    matched_by_external_id = 0
    matched_by_name = 0

    for row in kpi_sellers or []:
        external_id = str(_dict_value(row, "seller_external_id") or _dict_value(row, "external_id") or "").strip()
        seller_name = _dict_value(row, "seller_name") or _dict_value(row, "name")
        matched = None
        match_type = None
        if external_id:
            matched = next((user for user in user_identities if external_id in {value for value in user["external_ids"] if value}), None)
            if matched:
                match_type = "external_id"
        if not matched and seller_name and _training_kpi_normalize_name(seller_name) not in {"без имени", "unknown", "none"}:
            target = _training_kpi_normalize_name(seller_name)
            matched = next(
                (
                    user for user in user_identities
                    if any(
                        normalized and (normalized == target or normalized in target or target in normalized)
                        for normalized in [_training_kpi_normalize_name(str(name or "")) for name in user["names"]]
                    )
                ),
                None,
            )
            if matched:
                match_type = "name_fallback"
        kpi_payload = {
            "seller_external_id": external_id or None,
            "seller_name": seller_name,
            "store_name": _dict_value(row, "store_name"),
        }
        if matched:
            matched_user_ids.add(matched["id"])
            if match_type == "external_id":
                matched_by_external_id += 1
            else:
                matched_by_name += 1
            matches.append({"match_type": match_type, "confidence": "high" if match_type == "external_id" else "medium", "kpi_seller": kpi_payload, "user": {"id": matched["id"], "full_name": matched["full_name"], "email": matched["email"], "role": matched["role"]}})
        else:
            unresolved.append({**kpi_payload, "reason": "no_external_id_or_name_match" if external_id or seller_name else "missing_identity"})

    training_only = [
        {"id": user["id"], "full_name": user["full_name"], "email": user["email"], "role": user["role"]}
        for user in user_identities
        if user["id"] not in matched_user_ids
    ]
    recommendations: list[dict[str, str]] = []
    if unresolved:
        recommendations.append({"type": "mapping", "title": "Связать 1C-продавцов с аккаунтами обучения", "text": "Для несопоставленных KPI-строк заполните seller_external_id/onec_seller_id в профиле пользователя или подтвердите ручное соответствие."})
    if matched_by_name:
        recommendations.append({"type": "data_quality", "title": "Заменить name fallback на внешний ID", "text": "Совпадение по имени использовать только временно: однофамильцы и сокращения могут открыть чужую карточку."})

    return {
        "summary": {
            "total_kpi_sellers": len(kpi_sellers or []),
            "training_accounts": len(user_identities),
            "matched": len(matches),
            "matched_by_external_id": matched_by_external_id,
            "matched_by_name": matched_by_name,
            "unresolved": len(unresolved),
            "training_only": len(training_only),
        },
        "matches": matches,
        "unresolved": unresolved,
        "training_only": training_only,
        "recommendations": recommendations,
    }


def build_personal_training_kpi_summary_payload(*, seller: dict[str, Any] | None, training_profile: dict[str, Any] | None, program_cards: list[dict[str, Any]] | None = None, kpi: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = training_profile or {}
    cards = program_cards or []
    kpi_row = kpi or {}
    completed = int(profile.get("completed_steps") or 0)
    total = int(profile.get("total_steps") or 0)
    progress_percent = round((completed / total) * 100) if total else 0
    weakest = profile.get("weakest_competencies") or []
    recommended_focus = weakest[0].get("label") if weakest else "Закрепить GLAME-фразы, комплекты и продажи без давления"
    kpi_focus: list[str] = []
    completion_percent = _dict_value(kpi_row, "completion_percent")
    if completion_percent is not None and completion_percent < 80:
        kpi_focus.append("выполнение личного плана")
    if (_dict_value(kpi_row, "avg_check") or 0) and float(_dict_value(kpi_row, "avg_check") or 0) < 5000:
        kpi_focus.append("средний чек")
    if (_dict_value(kpi_row, "items_per_check") or 0) and float(_dict_value(kpi_row, "items_per_check") or 0) < 1.3:
        kpi_focus.append("изделий в чеке")
    priority = "high" if progress_percent < 50 and (completion_percent is None or completion_percent < 80) else "medium" if weakest or kpi_focus else "observe"
    next_card = next((card for card in cards if (card.get("next_action") or {}).get("target_id") or (card.get("progress") or {}).get("completed_steps", 0) < (card.get("progress") or {}).get("total_steps", 0)), cards[0] if cards else None)
    next_action = (next_card or {}).get("next_action") or {}
    manager_recommendation = "Назначить короткую тренировку по слабой компетенции перед ближайшей сменой и сверить результат по KPI." if priority == "high" else "Проверить динамику KPI после следующего принятого этапа обучения."
    return {
        "seller": seller or {},
        "level": profile.get("level"),
        "completed_steps": completed,
        "total_steps": total,
        "progress_percent": progress_percent,
        "attestation_ready": bool(profile.get("attestation_ready")),
        "achievements": profile.get("achievements") or [],
        "weakest_competencies": weakest,
        "next_program_title": ((next_card or {}).get("program") or {}).get("title"),
        "next_action": next_action,
        "recommended_training_focus": recommended_focus,
        "kpi_focus": kpi_focus,
        "priority": priority,
        "manager_recommendation": manager_recommendation,
    }


def build_seller_daily_training_focus_payload(*, seller: dict[str, Any] | None, training_summary: dict[str, Any] | None = None, kpi: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a seller-facing daily focus card connecting KPI and training.

    The tone is intentionally supportive: this is guidance for the next shift,
    not a manager score or punishment.
    """
    summary = training_summary or {}
    kpi_row = kpi or {}
    kpi_focus = list(summary.get("kpi_focus") or [])
    completion_percent = _dict_value(kpi_row, "completion_percent")
    if completion_percent is not None and float(completion_percent) < 80 and "выполнение личного плана" not in kpi_focus:
        kpi_focus.append("выполнение личного плана")
    if (_dict_value(kpi_row, "avg_check") or 0) and float(_dict_value(kpi_row, "avg_check") or 0) < 5000 and "средний чек" not in kpi_focus:
        kpi_focus.append("средний чек")
    if (_dict_value(kpi_row, "items_per_check") or 0) and float(_dict_value(kpi_row, "items_per_check") or 0) < 1.3 and "изделий в чеке" not in kpi_focus:
        kpi_focus.append("изделий в чеке")

    metric = kpi_focus[0] if kpi_focus else "сохранить темп и качество сервиса"
    focus = summary.get("recommended_training_focus") or "GLAME-фраза и продажа без давления"
    next_action = summary.get("next_action") or {}
    step_title = next_action.get("title") or next_action.get("label") or focus
    priority = summary.get("priority") or ("high" if completion_percent is not None and float(completion_percent) < 80 else "observe")

    if metric == "средний чек":
        recommended_action = "Сегодня тренируем спокойное предложение комплекта: к выбранному украшению показать 2–3 естественных продолжения образа и объяснить ценность без давления."
    elif metric == "изделий в чеке":
        recommended_action = "Сегодня добавляйте комплект мягко: серьги + кольцо/подвеска/уход как логичное завершение образа, а не как навязчивую допродажу."
    elif metric == "выполнение личного плана":
        recommended_action = "Сегодня держите фокус на первом контакте, поводе покупки и готовых вариантах: помогите клиенту быстрее увидеть подходящий образ."
    else:
        recommended_action = "Сегодня закрепите сильный сценарий: точный вопрос, спокойная GLAME-фраза и один понятный следующий шаг для клиента."

    return {
        "seller": seller or {},
        "priority": priority,
        "level": summary.get("level"),
        "progress_percent": summary.get("progress_percent", 0),
        "today_focus": {
            "metric": metric,
            "training_competency": focus,
            "kpi_completion_percent": completion_percent,
            "avg_check": _dict_value(kpi_row, "avg_check"),
            "items_per_check": _dict_value(kpi_row, "items_per_check"),
        },
        "training_step": {
            "program_title": summary.get("next_program_title"),
            "title": step_title,
            "target_id": next_action.get("target_id") or next_action.get("id"),
        },
        "recommended_action": recommended_action,
        "micro_practice": f"Перед сменой за 5 минут проговорите одну фразу по теме «{focus}» и примените ее на первом подходящем клиенте.",
        "mentor_prompt": f"Помоги сформулировать GLAME-фразу для темы: {focus}. KPI-фокус: {metric}.",
        "tone_guardrails": "Подсказка поддерживающая: без стыда, давления и резких оценок; финальные выводы подтверждает руководитель.",
        "weakest_competencies": summary.get("weakest_competencies") or [],
        "kpi_focus": kpi_focus,
    }


def _shift_value(shift: dict[str, Any], *keys: str):
    for key in keys:
        value = shift.get(key)
        if value not in (None, ""):
            return value
    return None


def build_schedule_aware_training_focus_payload(*, daily_focus: dict[str, Any], shifts: list[dict[str, Any]] | None = None, today: str | None = None, current_time: str | None = None) -> dict[str, Any]:
    """Adapt seller daily training focus to shift context.

    If a seller works today, the recommendation becomes pre-shift / in-shift /
    after-shift. If there is no shift, it stays light and preparatory.
    """
    payload = dict(daily_focus or {})
    shift_rows = shifts or []
    target_day = today or datetime.now(timezone.utc).date().isoformat()
    now_time = current_time or datetime.now(timezone.utc).strftime("%H:%M")

    def shift_date(row: dict[str, Any]) -> str:
        return str(_shift_value(row, "date", "shift_date", "work_date", "day") or "")[:10]

    sorted_shifts = sorted(shift_rows, key=lambda row: (shift_date(row), str(_shift_value(row, "start_time", "start", "time_from") or "")))
    today_shifts = [row for row in sorted_shifts if shift_date(row) == target_day]
    future_shifts = [row for row in sorted_shifts if shift_date(row) >= target_day]
    nearest = today_shifts[0] if today_shifts else (future_shifts[0] if future_shifts else None)

    if not nearest:
        context = {
            "mode": "no_shift",
            "title": "Сегодня без смены: легкая подготовка",
            "nearest_shift": None,
            "shift_count": len(shift_rows),
        }
        payload["schedule_context"] = context
        payload["micro_practice"] = f"Легкая подготовка без смены: {payload.get('micro_practice') or '5 минут повторить одну GLAME-фразу и пример комплекта.'}"
        return payload

    start_time = str(_shift_value(nearest, "start_time", "start", "time_from") or "")
    end_time = str(_shift_value(nearest, "end_time", "end", "time_to") or "")
    store_name = _shift_value(nearest, "store_name", "store", "shop_name")
    date_value = shift_date(nearest)
    if date_value == target_day and start_time and now_time < start_time:
        mode = "before_shift"
        title = "Перед сменой: короткая подготовка"
        practice_prefix = f"До начала смены в {start_time}"
    elif date_value == target_day and (not end_time or now_time <= end_time):
        mode = "during_shift"
        title = "Во время смены: применить фокус на клиенте"
        practice_prefix = "На смене"
    elif date_value == target_day:
        mode = "after_shift"
        title = "После смены: короткая рефлексия"
        practice_prefix = "После смены"
    else:
        mode = "upcoming_shift"
        title = "Ближайшая смена: подготовить фокус заранее"
        practice_prefix = f"К смене {date_value}"

    normalized_shift = {
        "date": date_value,
        "store_name": store_name,
        "start_time": start_time or None,
        "end_time": end_time or None,
    }
    payload["schedule_context"] = {"mode": mode, "title": title, "nearest_shift": normalized_shift, "shift_count": len(shift_rows)}
    if store_name and store_name not in str(payload.get("recommended_action") or ""):
        payload["recommended_action"] = f"{payload.get('recommended_action') or ''} Магазин фокуса: {store_name}.".strip()
    payload["micro_practice"] = f"{practice_prefix}: {payload.get('micro_practice') or '5 минут повторить одну GLAME-фразу.'}"
    return payload


def build_shift_reflection_payload(*, reflection: dict[str, Any] | None = None, daily_focus: dict[str, Any] | None = None, include_internal: bool = True) -> dict[str, Any]:
    """Evaluate after-shift reflection and prepare manager coaching signals.

    Seller-facing feedback stays supportive; risk flags are only for manager/admin.
    """
    data = reflection or {}
    focus = daily_focus or {}
    combined = " ".join(str(data.get(key) or "") for key in ["worked_well", "difficult_scenario", "glame_argument", "needs_help"]).lower()
    risk_flags: list[str] = []
    if any(word in combined for word in ["дорог", "цена", "сомневал", "возраж"]):
        risk_flags.append("price_objection")
    if any(word in combined for word in ["не получилось", "не смог", "сложно объяс", "сложно подобрать", "трудно", "растеря"]):
        risk_flags.append("needs_coaching")
    if len(str(data.get("worked_well") or "").strip()) < 12 or len(str(data.get("glame_argument") or "").strip()) < 12:
        risk_flags.append("low_detail")
    if str(data.get("needs_help") or "").strip():
        risk_flags.append("asked_for_help")

    positive_terms = ["комплект", "образ", "акцент", "цельн", "мягк", "объясн", "клиент"]
    ai_score = 5 + min(3, sum(1 for term in positive_terms if term in combined))
    if risk_flags:
        ai_score = max(4, ai_score - min(3, len(set(risk_flags))))
    status = "needs_coaching" if {"price_objection", "needs_coaching", "asked_for_help", "low_detail"}.intersection(risk_flags) else "completed"

    competency = ((focus.get("today_focus") or {}).get("training_competency") or (focus.get("training_step") or {}).get("title") or "GLAME-сервис")
    metric = (focus.get("today_focus") or {}).get("metric")
    seller_feedback = "Спасибо за рефлексию. Зафиксируйте удачный прием и выберите один маленький шаг для следующей смены."
    if status == "needs_coaching":
        seller_feedback = "Спасибо, это полезное наблюдение. Руководитель поможет разобрать сценарий и подобрать спокойную GLAME-фразу для следующей смены."
    manager_note = f"Руководителю: разобрать с продавцом сценарий после смены: {competency}."
    if "price_objection" in risk_flags:
        manager_note += " Особое внимание — объяснение ценности и работа с возражением по цене без давления."

    payload = {
        "status": status,
        "ai_score": min(10, max(1, ai_score)),
        "seller_feedback": seller_feedback,
        "manager_note": manager_note,
        "competency_links": [competency] if competency else [],
        "kpi_metric": metric,
        "reflection": data,
    }
    if include_internal:
        payload["risk_flags"] = sorted(set(risk_flags))
    return payload


# Backward-compatible alias for tests/consumers that use the normalized name.
def normalize_shift_reflection_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    return status if status in ALLOWED_SHIFT_REFLECTION_STATUSES else "submitted"


def normalize_coaching_action_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    return status if status in ALLOWED_COACHING_ACTION_STATUSES else "new"


def build_coaching_action_payload(
    *,
    reflection: dict[str, Any] | Any,
    manager_user_id: str | None = None,
    planned_for: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Create a manager-owned coaching action from a reflection/risk signal."""
    risk_flags = list(_dict_value(reflection, "risk_flags", []) or [])
    ai_evaluation = _dict_value(reflection, "ai_evaluation", {}) or {}
    competency_links = ai_evaluation.get("competency_links") or []
    competency = competency_links[0] if competency_links else "GLAME-сервис"
    kpi_metric = ai_evaluation.get("kpi_metric") or None
    store_name = _dict_value(reflection, "store_name")
    shift_date = _dict_value(reflection, "shift_date")
    reflection_id = _dict_value(reflection, "id")
    seller_user_id = _dict_value(reflection, "seller_user_id")

    if "price_objection" in risk_flags:
        topic = "Работа с возражением по цене через ценность образа"
        manager_script = "Разберите 1–2 реальные фразы клиента и соберите спокойный GLAME-ответ: ценность, эффект на образ, без давления."
        seller_next_step = "На следующей смене потренируйте одну фразу: объяснить ценность украшения через эффект на образ и предложить комплект мягко."
    elif "low_detail" in risk_flags:
        topic = "Уточнить конкретику клиентского сценария и GLAME-аргумент"
        manager_script = "Попросите продавца восстановить ситуацию: клиент, украшение, повод, фраза, следующий шаг. Дайте один пример сильной формулировки."
        seller_next_step = "В следующей рефлексии зафиксируйте конкретное украшение, сценарий клиента и одну спокойную фразу."
    elif "asked_for_help" in risk_flags or "needs_coaching" in risk_flags:
        topic = "Короткий разбор сложного клиентского сценария"
        manager_script = "Разберите сложность без оценки личности: что сказал клиент, какой вопрос задать, какую GLAME-фразу попробовать в следующий раз."
        seller_next_step = "Выберите один сложный сценарий и заранее подготовьте короткую GLAME-фразу для следующей смены."
    else:
        topic = "Закрепить удачный прием после смены"
        manager_script = "Отметьте сильный прием и договоритесь, где продавец повторит его на ближайшей смене."
        seller_next_step = "Повторите удачный прием на следующей смене и отметьте, как клиент отреагировал."

    planned_status = normalize_coaching_action_status(status or ("planned" if planned_for else "new"))
    return {
        "reflection_id": str(reflection_id) if reflection_id else None,
        "seller_user_id": str(seller_user_id) if seller_user_id else None,
        "created_by_user_id": str(manager_user_id) if manager_user_id else None,
        "status": planned_status,
        "planned_for": planned_for,
        "store_name": store_name,
        "shift_date": shift_date,
        "coaching_topic": topic,
        "competency": competency,
        "kpi_metric": kpi_metric,
        "risk_flags": sorted(set(risk_flags)),
        "manager_script": manager_script,
        "seller_next_step": seller_next_step,
        "source_manager_note": _dict_value(reflection, "manager_note"),
    }


def build_training_kpi_linkage_payload(*, seller_profiles: list[dict[str, Any]], kpi_sellers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Connect training progress with seller KPI rows for management decisions.

    This is intentionally correlation guidance, not causation proof. It highlights
    low training + weak KPI combinations so managers know which learning action to
    test next in shifts.
    """
    kpi_rows = kpi_sellers or []
    kpi_by_name = {_training_kpi_normalize_name(_dict_value(row, "seller_name")): row for row in kpi_rows if _dict_value(row, "seller_name")}
    matched_rows: list[dict[str, Any]] = []
    low_training_completion: list[float] = []
    trained_completion: list[float] = []
    seller_actions: list[dict[str, Any]] = []

    for item in seller_profiles:
        seller = item.get("seller") or {}
        profile = item.get("profile") or {}
        name = seller.get("full_name") or seller.get("email") or ""
        kpi = kpi_by_name.get(_training_kpi_normalize_name(name))
        if not kpi:
            continue
        completed = int(profile.get("completed_steps") or 0)
        total = int(profile.get("total_steps") or 0)
        training_percent = round((completed / total) * 100) if total else 0
        completion_percent = _dict_value(kpi, "completion_percent")
        if completion_percent is None:
            revenue = float(_dict_value(kpi, "revenue", 0) or 0)
            plan = float(_dict_value(kpi, "revenue_plan", 0) or 0)
            completion_percent = round(revenue / plan * 100, 1) if plan else None
        completion_value = float(completion_percent) if isinstance(completion_percent, (int, float)) else None
        if training_percent < 50 and completion_value is not None:
            low_training_completion.append(completion_value)
        elif training_percent >= 50 and completion_value is not None:
            trained_completion.append(completion_value)

        weakest = profile.get("weakest_competencies") or []
        recommended_focus = weakest[0].get("label") if weakest else "Закрепить сильные GLAME-фразы и продажи без давления"
        kpi_weaknesses: list[str] = []
        if completion_value is not None and completion_value < 80:
            kpi_weaknesses.append("выполнение личного плана")
        if (_dict_value(kpi, "avg_check") or 0) and float(_dict_value(kpi, "avg_check") or 0) < 5000:
            kpi_weaknesses.append("средний чек")
        if (_dict_value(kpi, "items_per_check") or 0) and float(_dict_value(kpi, "items_per_check") or 0) < 1.3:
            kpi_weaknesses.append("изделий в чеке")
        priority = "high" if training_percent < 50 and (completion_value is None or completion_value < 80) else "medium" if weakest or (completion_value is not None and completion_value < 100) else "observe"
        action = {
            "seller": seller,
            "store_name": _dict_value(kpi, "store_name"),
            "training": {
                "level": profile.get("level"),
                "completed_steps": completed,
                "total_steps": total,
                "percent": training_percent,
                "attestation_ready": bool(profile.get("attestation_ready")),
                "weakest_competencies": weakest,
            },
            "kpi": {
                "revenue": _dict_value(kpi, "revenue"),
                "revenue_plan": _dict_value(kpi, "revenue_plan"),
                "completion_percent": completion_percent,
                "avg_check": _dict_value(kpi, "avg_check"),
                "items_per_check": _dict_value(kpi, "items_per_check"),
                "checks": _dict_value(kpi, "checks"),
            },
            "priority": priority,
            "kpi_weaknesses": kpi_weaknesses,
            "recommended_training_focus": recommended_focus,
            "manager_action": "Назначить короткую отработку в ближайшую смену и проверить речевой скрипт после ответа." if priority == "high" else "Наблюдать динамику KPI после следующего принятого этапа обучения.",
        }
        matched_rows.append(action)
        if priority != "observe":
            seller_actions.append(action)

    low_kpi_and_low_training = len([item for item in matched_rows if item["training"]["percent"] < 50 and (item["kpi"]["completion_percent"] is None or item["kpi"]["completion_percent"] < 80)])
    recommendations: list[dict[str, str]] = []
    if low_kpi_and_low_training:
        recommendations.append({"type": "training_to_sales", "title": "Связать обучение с ближайшими сменами", "text": "У продавцов с низким прогрессом и слабым KPI назначьте практику по самой слабой компетенции прямо перед сменой."})
    if seller_actions:
        recommendations.append({"type": "manager_focus", "title": "Использовать обучение как рычаг KPI", "text": "В карточках продавцов показывайте не только план/факт, но и следующий учебный фокус: первый контакт, эффект на образ, средний чек или изделия в чеке."})

    return {
        "summary": {
            "matched_sellers": len(matched_rows),
            "low_kpi_and_low_training": low_kpi_and_low_training,
            "avg_completion_low_training": _safe_round_average(low_training_completion),
            "avg_completion_trained": _safe_round_average(trained_completion),
        },
        "seller_actions": sorted(seller_actions, key=lambda item: ({"high": 0, "medium": 1, "observe": 2}.get(item["priority"], 3), item["seller"].get("full_name") or ""))[:12],
        "recommendations": recommendations,
        "note": "Связка обучения и KPI показывает управленческие гипотезы, а не доказывает причинность. Проверять через смены и динамику продаж.",
    }


def build_management_analytics_payload(*, seller_profiles: list[dict[str, Any]], step_submissions: list[Any] | None = None, mentor_messages: list[Any] | None = None, attestations: list[Any] | None = None) -> dict[str, Any]:
    submissions = step_submissions or []
    messages = mentor_messages or []
    attest = attestations or []
    active_learners = len(seller_profiles)
    zero_progress = 0
    attestation_ready = 0
    risk_sellers: list[dict[str, Any]] = []
    competency_heatmap: dict[str, dict[str, Any]] = {}

    for item in seller_profiles:
        seller = item.get("seller") or {}
        profile = item.get("profile") or {}
        completed = int(profile.get("completed_steps") or 0)
        total = int(profile.get("total_steps") or 0)
        if completed == 0:
            zero_progress += 1
        if profile.get("attestation_ready"):
            attestation_ready += 1
        if completed == 0 or profile.get("weakest_competencies"):
            risk_sellers.append({"seller": seller, "completed_steps": completed, "total_steps": total, "weakest_competencies": profile.get("weakest_competencies") or []})
        for competency in profile.get("weakest_competencies") or []:
            code = competency.get("code") or competency.get("label")
            stat = competency_heatmap.setdefault(code, {"code": code, "label": competency.get("label") or code, "risk_count": 0, "percent_sum": 0})
            stat["risk_count"] += 1
            stat["percent_sum"] += int(competency.get("percent") or 0)

    for stat in competency_heatmap.values():
        stat["average_percent"] = round(stat["percent_sum"] / stat["risk_count"]) if stat["risk_count"] else 0
        stat.pop("percent_sum", None)

    pending_reviews = sum(1 for submission in submissions if _dict_value(submission, "review_status") in {"review_pending", "revision_draft", "revision_requested"})
    revision_count = sum(1 for submission in submissions if _dict_value(submission, "review_status") in {"revision_draft", "revision_requested"})
    bottlenecks: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        status = _dict_value(submission, "review_status")
        if status in {"revision_draft", "revision_requested", "review_pending"}:
            title = _dict_value(submission, "step_title") or "Этап программы"
            item = bottlenecks.setdefault(title, {"step_title": title, "pending_or_revision": 0, "revision_count": 0})
            item["pending_or_revision"] += 1
            if status in {"revision_draft", "revision_requested"}:
                item["revision_count"] += 1

    mentor_risk_count = sum(1 for message in messages if _dict_value(message, "risk_flags", []) or [])
    tag_counts: dict[str, dict[str, Any]] = {}
    for message in messages:
        context = _dict_value(message, "context", {}) or {}
        for tag in context.get("focus_tags", []) or []:
            item = tag_counts.setdefault(tag, {"tag": tag, "count": 0})
            item["count"] += 1

    attestation_pending = sum(1 for item in attest if _dict_value(item, "status") in {"submitted", "review_pending"})
    certified = sum(1 for item in attest if _dict_value(item, "status") == "certified")

    recommendations: list[dict[str, str]] = []
    if zero_progress:
        recommendations.append({"type": "activation", "title": "Запустить стажеров без прогресса", "text": "Назначьте первый обязательный этап и короткую проверку после смены."})
    if revision_count:
        recommendations.append({"type": "content", "title": "Повторить сложные этапы", "text": "Этапы с доработками стоит разобрать на планерке и усилить примерами GLAME-фраз."})
    if mentor_risk_count:
        recommendations.append({"type": "manager_review", "title": "Проверить вопросы к AI-наставнику", "text": "Есть вопросы, где продавец просил оценку или аттестационное решение. Руководитель должен дать финальную обратную связь."})
    if attestation_ready:
        recommendations.append({"type": "attestation", "title": "Открыть аттестации готовым сотрудникам", "text": "Сотрудники с закрытыми базовыми компетенциями готовы к сертификационному кейсу."})

    return {
        "summary": {
            "active_learners": active_learners,
            "zero_progress": zero_progress,
            "pending_reviews": pending_reviews,
            "revision_count": revision_count,
            "attestation_ready": attestation_ready,
            "attestation_pending": attestation_pending,
            "certified": certified,
            "mentor_risk_count": mentor_risk_count,
        },
        "risk_sellers": risk_sellers[:10],
        "competency_heatmap": sorted(competency_heatmap.values(), key=lambda item: (-item["risk_count"], item["average_percent"], item["code"])),
        "submission_bottlenecks": sorted(bottlenecks.values(), key=lambda item: (-item["pending_or_revision"], -item["revision_count"], item["step_title"])),
        "mentor_focus_tags": sorted(tag_counts.values(), key=lambda item: (-item["count"], item["tag"])),
        "recommendations": recommendations,
    }


def build_competency_profile_payload(*, steps: list[Any], step_progress: dict[str, dict] | None = None) -> dict[str, Any]:
    progress = step_progress or {}
    competency_stats: dict[str, dict[str, Any]] = {}
    completed_steps = 0
    scores: list[int] = []

    for step in steps:
        step_id = str(_dict_value(step, "id"))
        current = progress.get(step_id, {})
        accepted = current.get("status") == "accepted"
        score = current.get("score")
        if accepted:
            completed_steps += 1
        if isinstance(score, (int, float)):
            scores.append(int(score))
        for code in _dict_value(step, "competencies", []) or []:
            stat = competency_stats.setdefault(
                code,
                {"code": code, "label": COMPETENCY_LABELS.get(code, code), "total_steps": 0, "accepted_steps": 0, "score_sum": 0, "score_count": 0},
            )
            stat["total_steps"] += 1
            if accepted:
                stat["accepted_steps"] += 1
            if isinstance(score, (int, float)):
                stat["score_sum"] += int(score)
                stat["score_count"] += 1

    for stat in competency_stats.values():
        total = stat["total_steps"] or 0
        stat["percent"] = round((stat["accepted_steps"] / total) * 100) if total else 0
        stat["average_score"] = round(stat["score_sum"] / stat["score_count"], 1) if stat["score_count"] else None
        stat.pop("score_sum", None)
        stat.pop("score_count", None)

    average_score = round(sum(scores) / len(scores), 1) if scores else None
    if completed_steps >= 20 and (average_score or 0) >= 8:
        level = "Senior Stylist"
    elif completed_steps >= 12 and (average_score or 0) >= 7:
        level = "Styлист GLAME"
    elif completed_steps >= 6:
        level = "Consultant"
    elif completed_steps >= 2:
        level = "Junior Consultant"
    else:
        level = "Стажер"

    achievements: list[dict[str, str]] = []
    if completed_steps >= 1:
        achievements.append({"code": "first_step", "title": "Первый этап пройден", "description": "Сотрудник завершил первый этап программы."})
    if competency_stats.get("service_contact", {}).get("accepted_steps", 0) >= 2:
        achievements.append({"code": "service_foundation", "title": "Сервисная база", "description": "Закрыты ключевые шаги первого контакта."})
    if len([score for score in scores if score >= 8]) >= 2:
        achievements.append({"code": "high_quality_answers", "title": "Сильные ответы", "description": "Несколько ответов получили высокую AI-предоценку."})
    if competency_stats.get("styling_effect", {}).get("percent", 0) >= 100:
        achievements.append({"code": "styling_effect", "title": "Эффект на образ", "description": "Освоено объяснение украшений через эффект на образ."})

    weakest = sorted(competency_stats.values(), key=lambda item: (item["percent"], item["accepted_steps"], item["code"]))[:3]
    strongest = sorted(competency_stats.values(), key=lambda item: (-item["percent"], -item["accepted_steps"], item["code"]))[:3]
    return {
        "level": level,
        "completed_steps": completed_steps,
        "total_steps": len(steps),
        "average_score": average_score,
        "competencies": competency_stats,
        "strongest_competencies": strongest,
        "weakest_competencies": weakest,
        "achievements": achievements,
        "attestation_ready": completed_steps >= 4 and all(stat["percent"] >= 50 for stat in competency_stats.values()),
    }


def normalize_step_submission_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    if status in ALLOWED_STEP_SUBMISSION_STATUSES:
        return status
    return "review_pending"


def _step_progress_status(review_status: str | None) -> str:
    status = normalize_step_submission_status(review_status)
    if status == "accepted" or status == "sent_to_consultant":
        return "accepted"
    if status in {"revision_draft", "revision_requested"}:
        return "needs_revision"
    return "submitted"


def apply_step_submission_progress(*, current_meta: dict[str, Any] | None, step_id: str, submission_id: str, review_status: str, ai_score: int | None = None) -> dict[str, Any]:
    meta = dict(current_meta or {})
    progress = dict(meta.get("step_progress") or {})
    progress[str(step_id)] = {
        **(progress.get(str(step_id)) or {}),
        "status": _step_progress_status(review_status),
        "submission_id": str(submission_id),
        "review_status": normalize_step_submission_status(review_status),
        "score": ai_score,
    }
    meta["step_progress"] = progress
    return meta


def build_step_submission_payload(*, submission: Any, step: Any = None, include_internal: bool = False) -> dict[str, Any]:
    review_status = normalize_step_submission_status(_dict_value(submission, "review_status", None) or _dict_value(submission, "status", None))
    consultant_feedback = _dict_value(submission, "consultant_feedback", None)
    if not include_internal and review_status not in {"sent_to_consultant", "accepted"}:
        consultant_feedback = None
    payload = {
        "id": str(_dict_value(submission, "id")),
        "program_id": str(_dict_value(submission, "program_id")),
        "step_id": str(_dict_value(submission, "step_id")),
        "step_title": _dict_value(step, "title"),
        "competencies": _dict_value(step, "competencies", []) or [],
        "seller_user_id": str(_dict_value(submission, "seller_user_id")),
        "practice_answer": _dict_value(submission, "practice_answer"),
        "evening_review": _dict_value(submission, "evening_review"),
        "ai_score": _dict_value(submission, "ai_score"),
        "status": review_status,
        "review_status": review_status,
        "manager_feedback": _dict_value(submission, "manager_feedback"),
        "consultant_feedback": consultant_feedback,
        "created_at": _dict_value(submission, "created_at"),
        "reviewed_at": _dict_value(submission, "reviewed_at"),
    }
    if include_internal:
        payload["ai_evaluation"] = _dict_value(submission, "ai_evaluation", {}) or {}
    return payload


def _contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def evaluate_submission_quality(answer: str | None, *, expected_focus: str | None = None) -> dict[str, Any]:
    """Rule-based first-pass quality check for consultant training answers.

    This intentionally produces a manager-review draft, not direct consultant feedback.
    """
    text = (answer or "").strip()
    lower = text.lower()
    score = 0
    criteria: dict[str, int] = {
        "topic_understanding": 0,
        "specific_jewelry_or_scenario": 0,
        "image_effect": 0,
        "glame_language": 0,
        "practical_use": 0,
    }

    if len(text) >= 80:
        criteria["topic_understanding"] = 1
    if expected_focus and any(part in lower for part in expected_focus.lower().split()[:3]):
        criteria["topic_understanding"] = max(criteria["topic_understanding"], 1)
    if len(text) >= 160 and _contains_any(text, POSITIVE_EFFECT_TERMS):
        criteria["topic_understanding"] = 2

    if any(word in lower for word in ["серьг", "кольц", "браслет", "подвес", "колье", "кафф", "украшен"]):
        criteria["specific_jewelry_or_scenario"] = 1
    if any(word in lower for word in ["рубаш", "плать", "жакет", "встреч", "событ", "каждый день", "вечер"]):
        criteria["specific_jewelry_or_scenario"] = 2

    effect_hits = sum(1 for term in POSITIVE_EFFECT_TERMS if term in lower)
    if effect_hits >= 1:
        criteria["image_effect"] = 1
    if effect_hits >= 3:
        criteria["image_effect"] = 2

    if not _contains_any(text, WEAK_OR_FORBIDDEN_TERMS):
        criteria["glame_language"] = 1
    if criteria["glame_language"] and effect_hits >= 2 and any(term in lower for term in ["не перегруж", "спокой", "цельн", "собран"]):
        criteria["glame_language"] = 2

    if any(word in lower for word in ["клиент", "фраз", "можно сказать", "предлож", "следующим шагом", "подобрать"]):
        criteria["practical_use"] = 1
    if criteria["practical_use"] and any(word in lower for word in ["с чем", "носить", "после", "следующим шагом"]):
        criteria["practical_use"] = 2

    score = sum(criteria.values())
    if _contains_any(text, WEAK_OR_FORBIDDEN_TERMS):
        score = max(0, score - 2)

    if score <= REVISION_THRESHOLD:
        recommendation = "request_revision"
        status = "revision_draft"
        review_comment = (
            "Спасибо, задание получено. Давайте немного доработаем ответ, чтобы он был полезнее "
            "для работы в зале: выберите конкретное украшение, объясните, что оно даёт образу, "
            "с чем его можно носить и какой спокойной фразой GLAME вы скажете это клиенту."
        )
    else:
        recommendation = "accept" if score >= ACCEPT_THRESHOLD else "needs_manager_comment"
        status = "feedback_review"
        review_comment = (
            "Ответ можно вынести на проверку руководителю. В нём уже есть практическая основа; "
            "при проверке стоит уточнить, достаточно ли явно связаны украшение, сценарий клиента и эффект на образ."
        )

    return {
        "score": score,
        "max_score": 10,
        "criteria": criteria,
        "recommendation": recommendation,
        "status": status,
        "review_comment": review_comment,
    }


def should_request_revision(evaluation: dict[str, Any] | None) -> bool:
    if not evaluation:
        return False
    return evaluation.get("recommendation") == "request_revision" or int(evaluation.get("score") or 0) <= REVISION_THRESHOLD
