from __future__ import annotations

import base64
import binascii
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.agent_system_prompt import AgentSystemPrompt
from app.models.consultant_training import (
    ConsultantTrainingAssignment,
    ConsultantTrainingAttestation,
    ConsultantTrainingCoachingAction,
    ConsultantTrainingEnrollment,
    ConsultantTrainingMaterial,
    ConsultantTrainingMaterialSlide,
    ConsultantTrainingMaterialSlideProgress,
    ConsultantTrainingMaterialStatusHistory,
    ConsultantTrainingMentorMessage,
    ConsultantTrainingModule,
    ConsultantTrainingProgram,
    ConsultantTrainingShiftReflection,
    ConsultantTrainingStep,
    ConsultantTrainingStepMaterial,
    ConsultantTrainingStepSubmission,
    ConsultantTrainingSubmission,
    ConsultantTrainingTopic,
)
from app.models.user import User
from app.services.admin_access import normalize_role
from app.services.seller_kpi_service import SellerKPIService
from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env
from app.services.consultant_training_service import (
    apply_step_submission_progress,
    build_attestation_payload,
    build_coaching_action_payload,
    build_competency_profile_payload,
    build_mentor_message_payload,
    build_mentor_reply,
    build_mentor_reply_with_library_context,
    build_management_analytics_payload,
    build_personal_training_kpi_summary_payload,
    build_seller_training_account_matching_payload,
    build_seller_training_account_preferences_update,
    build_seller_daily_training_focus_payload,
    build_current_learning_task_payload,
    build_training_mentor_session_payload,
    build_seller_career_level_payload,
    build_team_career_levels_payload,
    build_schedule_aware_training_focus_payload,
    build_shift_reflection_payload,
    build_training_kpi_linkage_payload,
    build_training_material_library_payload,
    build_training_material_payload,
    build_training_material_source_file_payload,
    build_training_material_visual_assets_payload,
    build_training_material_visual_asset_update_payload,
    build_training_material_search_payload,
    build_training_material_context_payload,
    build_training_material_bulk_import_payload,
    build_document_extractor_status_payload,
    build_training_material_retry_extraction_payload,
    build_training_material_extraction_review_payload,
    parse_training_material_document_import,
    build_training_material_publish_gate_payload,
    build_training_material_detail_payload,
    build_training_material_status_change_payload,
    build_training_material_publish_cascade_payload,
    build_training_material_slide_payload,
    build_training_material_slides_payload,
    build_training_material_slides_progress_payload,
    build_training_material_progress_analytics_payload,
    build_training_material_learning_pack_payload,
    DEFAULT_TRAINING_MATERIAL_REFORMATTER_PROMPT,
    TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
    build_step_material_practice_gate_payload,
    build_step_material_link_payload,
    build_unlocked_step_materials_payload,
    build_program_assignment_removal_payload,
    build_program_card_payload,
    build_program_structure_payload,
    build_step_submission_payload,
    ensure_consultant_training_schema,
    evaluate_submission_quality,
    normalize_program_status,
    normalize_step_submission_status,
    normalize_shift_reflection_status,
    normalize_coaching_action_status,
    normalize_training_material_status,
    normalize_topic_status,
    should_request_revision,
)

MANAGER_ROLES = ["admin", "manager", "marketer"]
SELLER_ROLES = ["admin", "manager", "seller"]

router = APIRouter()


class TopicCreateRequest(BaseModel):
    lesson_date: date
    title: str = Field(min_length=1, max_length=255)
    theme: str | None = None
    goal: str | None = None
    material_text: str | None = None
    assignment_text: str | None = None
    focus_text: str | None = None
    status: str = "draft"
    meta: dict = Field(default_factory=dict)


class TopicUpdateRequest(BaseModel):
    lesson_date: date | None = None
    title: str | None = None
    theme: str | None = None
    goal: str | None = None
    material_text: str | None = None
    assignment_text: str | None = None
    focus_text: str | None = None
    status: str | None = None
    approval_comment: str | None = None
    meta: dict | None = None


class TopicApprovalRequest(BaseModel):
    approved: bool = True
    comment: str | None = None


class VoiceAnswerRequest(BaseModel):
    filename: str | None = None
    mime_type: str | None = None
    content_base64: str | None = None
    transcript: str | None = None
    duration_seconds: float | None = None
    source: str = "uploaded"


class SubmissionCreateRequest(BaseModel):
    practice_answer: str | None = None
    evening_review: str | None = None
    voice_answer: VoiceAnswerRequest | None = None


class SubmissionReviewRequest(BaseModel):
    review_status: str = Field(default="approved")
    manager_feedback: str | None = None
    consultant_feedback: str | None = None
    send_to_consultant: bool = False


class ProgramCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    program_type: str = "custom"
    status: str = "active"
    audience_rules: dict = Field(default_factory=dict)
    is_required: bool = True
    order_index: int = 100
    meta: dict = Field(default_factory=dict)


class ModuleCreateRequest(BaseModel):
    program_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    order_index: int = 100
    meta: dict = Field(default_factory=dict)


class StepCreateRequest(BaseModel):
    module_id: UUID
    title: str = Field(min_length=1, max_length=255)
    lesson_text: str | None = None
    practice_text: str | None = None
    answer_template: str | None = None
    assessment_rubric: dict = Field(default_factory=dict)
    competencies: list[str] = Field(default_factory=list)
    unlock_rule: dict = Field(default_factory=dict)
    is_required: bool = True
    order_index: int = 100
    meta: dict = Field(default_factory=dict)


class StepSubmissionCreateRequest(BaseModel):
    practice_answer: str | None = None
    evening_review: str | None = None
    voice_answer: VoiceAnswerRequest | None = None


class StepSubmissionReviewRequest(BaseModel):
    review_status: str = Field(default="accepted")
    manager_feedback: str | None = None
    consultant_feedback: str | None = None
    send_to_consultant: bool = False


class AttestationStartRequest(BaseModel):
    program_id: UUID
    attestation_type: str = "trainee_final"


class AttestationSubmitRequest(BaseModel):
    answer_payload: dict = Field(default_factory=dict)


class AttestationReviewRequest(BaseModel):
    manager_decision: str = "passed"
    manager_feedback: str | None = None
    certified_level: str | None = None


class MentorAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    program_id: UUID | None = None
    step_id: UUID | None = None
    context: dict = Field(default_factory=dict)


class TrainingMaterialCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    topic: str = Field(default="Общее", max_length=255)
    category: str = Field(default="Библиотека GLAME", max_length=255)
    description: str | None = None
    markdown_content: str = Field(min_length=1)
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    source_type: str = "manual_md"
    program_code: str | None = None
    competencies: list[str] = Field(default_factory=list)
    internal_notes: str | None = None
    order_index: int = 100


class TrainingMaterialUpdateRequest(BaseModel):
    title: str | None = None
    topic: str | None = None
    category: str | None = None
    description: str | None = None
    markdown_content: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    source_type: str | None = None
    program_code: str | None = None
    competencies: list[str] | None = None
    internal_notes: str | None = None
    order_index: int | None = None
    status_note: str | None = None


class TrainingProgramAssignmentRequest(BaseModel):
    seller_user_id: UUID
    program_id: UUID
    status: str = "available"
    lock_other_programs: bool = True
    note: str | None = None


class TrainingProgramUnassignRequest(BaseModel):
    archive: bool = False


class TrainingProgramAccessRequest(BaseModel):
    message: str | None = None


class TrainingMaterialImportFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content: str | None = None
    content_base64: str | None = None
    mime_type: str | None = None


class TrainingMaterialBulkImportRequest(BaseModel):
    files: list[TrainingMaterialImportFileRequest] = Field(default_factory=list)
    default_topic: str = "Общее"
    default_category: str = "Импорт документов"
    default_status: str = "draft"
    default_program_code: str | None = None
    auto_generate_learning_pack: bool = True
    dry_run: bool = False


class TrainingMaterialRetryExtractionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content: str | None = None
    content_base64: str | None = None
    mime_type: str | None = None
    note: str | None = None
    mark_reviewed: bool = True


class TrainingMaterialExtractionReviewRequest(BaseModel):
    reviewed_markdown: str = Field(min_length=1)
    note: str | None = None


class TrainingMaterialSlideRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str | None = None
    image_url: str | None = None
    image_prompt: str | None = None
    speaker_note: str | None = None
    quiz_question: str | None = None
    status: str = "draft"
    order_index: int = 100
    meta: dict = Field(default_factory=dict)


class TrainingMaterialVisualAssetReviewRequest(BaseModel):
    status: str = "approved"
    note: str | None = None
    slide_id: UUID | None = None
    apply_to_slide: bool = False


class TrainingMaterialVisualAssetsAttachAllRequest(BaseModel):
    create_missing_slides: bool = True
    replace_existing_slide_images: bool = False
    note: str | None = "Все визуалы подтверждены и добавлены в draft-слайды руководителем"


class TrainingMaterialLearningPackRequest(BaseModel):
    target_slide_count: int = Field(default=5, ge=3, le=7)
    apply: bool = False
    replace_existing_draft_slides: bool = False
    replace_all_slides: bool = False


class StepMaterialLinkRequest(BaseModel):
    program_id: UUID
    module_id: UUID | None = None
    step_id: UUID
    material_id: UUID
    role: str = "primary_lesson"
    required_to_complete: bool = True
    order_index: int = 100
    meta: dict = Field(default_factory=dict)


class PersonalTrainingSummaryRequest(BaseModel):
    seller_external_id: str | None = None
    seller_name: str | None = None
    store_name: str | None = None
    kpi: dict = Field(default_factory=dict)


class TrainingAccountLinkRequest(BaseModel):
    user_id: UUID
    seller_external_id: str = Field(min_length=1, max_length=255)
    seller_name: str | None = None
    store_name: str | None = None


class ShiftReflectionCreateRequest(BaseModel):
    shift_date: date | None = None
    store_name: str | None = None
    worked_well: str = Field(min_length=1, max_length=4000)
    difficult_scenario: str | None = None
    glame_argument: str = Field(min_length=1, max_length=4000)
    needs_help: str | None = None
    daily_focus: dict = Field(default_factory=dict)


class ShiftReflectionReviewRequest(BaseModel):
    status: str = "reviewed"
    manager_feedback: str | None = None


class CoachingActionCreateRequest(BaseModel):
    reflection_id: UUID | None = None
    seller_user_id: UUID | None = None
    planned_for: date | None = None
    coaching_topic: str | None = None
    manager_script: str | None = None
    seller_next_step: str | None = None


class CoachingActionUpdateRequest(BaseModel):
    status: str | None = None
    planned_for: date | None = None
    manager_result: str | None = None
    seller_visible_feedback: str | None = None


def iso(value):
    return value.isoformat() if value else None


VOICE_ANSWER_UPLOAD_ROOT = Path("uploads") / "training_voice_answers"
VOICE_ANSWER_MAX_BYTES = 15 * 1024 * 1024
VOICE_ANSWER_MIME_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
}


def build_voice_answer_metadata(payload: VoiceAnswerRequest | None, *, current_user: User) -> dict | None:
    if not payload:
        return None
    transcript = (payload.transcript or "").strip()
    content_base64 = (payload.content_base64 or "").strip()
    mime_type = (payload.mime_type or "audio/webm").split(";", 1)[0].strip().lower()
    source = (payload.source or "uploaded").strip()[:40] or "uploaded"
    metadata: dict = {
        "required_oral_answer": True,
        "source": source,
        "transcript": transcript or None,
        "transcription_status": "browser_transcribed" if transcript else "pending_transcription",
        "duration_seconds": payload.duration_seconds,
        "filename": (payload.filename or "voice-answer").strip()[:180],
        "mime_type": mime_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if content_base64:
        if mime_type not in VOICE_ANSWER_MIME_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Поддерживаются только аудиофайлы для голосового ответа")
        try:
            audio_bytes = base64.b64decode(content_base64.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="Некорректный base64 голосового ответа")
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Голосовой файл пустой")
        if len(audio_bytes) > VOICE_ANSWER_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Голосовой ответ слишком большой, максимум 15 МБ")
        ext = VOICE_ANSWER_MIME_EXTENSIONS[mime_type]
        user_dir = VOICE_ANSWER_UPLOAD_ROOT / str(current_user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4()}.{ext}"
        stored_path = user_dir / stored_filename
        stored_path.write_bytes(audio_bytes)
        metadata.update({
            "audio_url": f"/uploads/training_voice_answers/{current_user.id}/{stored_filename}",
            "size_bytes": len(audio_bytes),
            "transcription_status": "browser_transcribed" if transcript else "pending_transcription",
        })
    elif not transcript:
        raise HTTPException(status_code=400, detail="Нужно приложить голосовой файл или текст транскрибации")
    return metadata


def build_answer_text_with_voice(practice_answer: str | None, voice_metadata: dict | None) -> str:
    text = (practice_answer or "").strip()
    if text:
        return text
    if voice_metadata and voice_metadata.get("transcript"):
        return str(voice_metadata.get("transcript") or "").strip()
    if voice_metadata:
        return "[Голосовой ответ продавца загружен. Транскрибация ожидает обработки.]"
    raise HTTPException(status_code=422, detail="Нужно дать ответ текстом или приложить голосовой ответ")


def attach_voice_metadata_to_evaluation(evaluation: dict, voice_metadata: dict | None) -> dict:
    if not voice_metadata:
        return evaluation
    enriched = dict(evaluation or {})
    enriched["voice_answer"] = voice_metadata
    notes = list(enriched.get("notes") or [])
    notes.append("Ответ получен устно: проверка должна учитывать транскрибацию голосового файла и подлинность ответа продавца.")
    if voice_metadata.get("transcription_status") == "pending_transcription":
        notes.append("Транскрибация голосового ответа пока не выполнена; AI-оценка по тексту является предварительной.")
    enriched["notes"] = notes
    return enriched


async def get_active_training_reformatter_prompt(db: AsyncSession) -> tuple[str, dict]:
    """Load editable prompt for source-doc -> learning-pack agent, with safe fallback."""
    result = await db.execute(
        select(AgentSystemPrompt)
        .where(
            AgentSystemPrompt.agent_type == TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
            AgentSystemPrompt.is_active == True,
        )
        .order_by(desc(AgentSystemPrompt.version))
        .limit(1)
    )
    prompt = result.scalars().first()
    if prompt and (prompt.system_prompt or "").strip():
        return prompt.system_prompt.strip(), {
            "agent_type": TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
            "prompt_source": "active_system_prompt",
            "prompt_id": str(prompt.id),
            "version": prompt.version,
            "name": prompt.name,
        }
    return DEFAULT_TRAINING_MATERIAL_REFORMATTER_PROMPT, {
        "agent_type": TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
        "prompt_source": "code_fallback_default",
        "prompt_id": None,
        "version": None,
        "name": "Default training material reformatter prompt",
    }


def build_learning_pack_generation_user_prompt(material_payload: dict, target_slide_count: int) -> str:
    return (
        "Переформатируй исходный учебный материал GLAME в draft learning pack для продавца.\n\n"
        f"Количество слайдов: {target_slide_count}.\n"
        f"Название материала: {material_payload.get('title') or 'Учебный материал'}\n"
        f"Тема: {material_payload.get('topic') or 'Общее'}\n"
        f"Категория: {material_payload.get('category') or 'Общее'}\n"
        f"Программа: {material_payload.get('program_code') or 'не указана'}\n"
        f"Теги: {', '.join(material_payload.get('tags') or [])}\n\n"
        "Исходник:\n"
        f"{(material_payload.get('markdown_content') or '')[:12000]}"
    )


def learning_pack_response_format(target_slide_count: int) -> dict:
    return {
        "slides": [
            {
                "title": "string",
                "body": "string",
                "image_prompt": "string, admin-only visual generation prompt",
                "speaker_note": "string, admin-only manager note",
                "quiz_question": "string",
                "order_index": "integer",
            }
        ],
        "practice": {
            "task": "string",
            "answer_template": ["string"],
        },
        "assessment": {
            "criteria": ["string"],
            "manager_review_note": "string",
            "question_pool": [
                {
                    "question": "string",
                    "type": "short_answer | client_scenario | do_dont | shift_application | multiple_choice",
                    "difficulty": "easy | medium | hard",
                    "expected_answer": "string",
                    "criteria": ["string"],
                }
            ],
        },
        "target_slide_count": target_slide_count,
    }


def parse_structured_agent_json(raw_content: str) -> dict:
    response = (raw_content or "").strip()
    if not response:
        return {"raw_response": "", "parse_error": "Пустой текст в ответе модели"}
    if "```json" in response:
        response = response.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in response:
        response = response.split("```", 1)[1].split("```", 1)[0]
    response = response.strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(response[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"raw_response": raw_content[:2000], "parse_error": "Не удалось распознать JSON в ответе"}


def merge_agent_learning_pack_payload(base_pack: dict, generated: dict, prompt_info: dict) -> dict:
    slides = generated.get("slides") if isinstance(generated, dict) else None
    if not isinstance(slides, list) or not slides:
        base_pack["agent"] = {**prompt_info, "generation_mode": "deterministic_fallback", "llm_parse_error": generated.get("parse_error") if isinstance(generated, dict) else "invalid_response"}
        return base_pack
    base_slides = base_pack.get("slides") if isinstance(base_pack.get("slides"), list) else []
    normalized_slides = []
    for index, slide in enumerate(slides[:7], start=1):
        if not isinstance(slide, dict):
            continue
        base_slide = base_slides[index - 1] if index - 1 < len(base_slides) and isinstance(base_slides[index - 1], dict) else {}
        title = str(slide.get("title") or f"Слайд {index}").strip()[:255]
        body = str(slide.get("body") or "").strip()
        if not body:
            continue
        try:
            order_index = int(slide.get("order_index") or index * 10)
        except (TypeError, ValueError):
            order_index = index * 10
        normalized_slides.append({
            "title": title,
            "body": body,
            "image_url": slide.get("image_url") or base_slide.get("image_url"),
            "image_prompt": str(slide.get("image_prompt") or base_slide.get("image_prompt") or f"GLAME premium jewelry training visual, слайд {index}, clean editorial style").strip() if not (slide.get("image_url") or base_slide.get("image_url")) else None,
            "speaker_note": str(slide.get("speaker_note") or "Для руководителя: проверить соответствие стандартам GLAME перед публикацией.").strip(),
            "quiz_question": str(slide.get("quiz_question") or "Что главное нужно применить в работе после этого слайда?").strip(),
            "status": "draft",
            "order_index": order_index,
            "content_format": "learning_slide",
            "meta": {**(base_slide.get("meta") or {}), **(slide.get("meta") or {})},
        })
    if normalized_slides:
        base_pack["slides"] = normalized_slides
    practice = generated.get("practice") if isinstance(generated, dict) else None
    if isinstance(practice, dict):
        if practice.get("task"):
            base_pack.setdefault("practice", {})["task"] = str(practice.get("task"))
        if isinstance(practice.get("answer_template"), list):
            base_pack.setdefault("practice", {})["answer_template"] = [str(item) for item in practice.get("answer_template") if str(item).strip()]
    assessment = generated.get("assessment") if isinstance(generated, dict) else None
    if isinstance(assessment, dict):
        if isinstance(assessment.get("criteria"), list):
            base_pack.setdefault("assessment", {})["criteria"] = [str(item) for item in assessment.get("criteria") if str(item).strip()]
        if assessment.get("manager_review_note"):
            base_pack.setdefault("assessment", {})["manager_review_note"] = str(assessment.get("manager_review_note"))
        if isinstance(assessment.get("question_pool"), list):
            question_pool = []
            for index, item in enumerate(assessment.get("question_pool") or [], start=1):
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question") or "").strip()
                if not question:
                    continue
                question_pool.append({
                    "question": question,
                    "type": str(item.get("type") or "short_answer").strip()[:60],
                    "difficulty": str(item.get("difficulty") or "medium").strip()[:40],
                    "expected_answer": str(item.get("expected_answer") or item.get("answer") or "Ответ должен показать понимание материала и корректное применение в GLAME-языке.").strip(),
                    "criteria": [str(criterion) for criterion in (item.get("criteria") or []) if str(criterion).strip()],
                    "order_index": int(item.get("order_index") or index * 10) if str(item.get("order_index") or "").isdigit() else index * 10,
                    "review_required": True,
                })
            if question_pool:
                base_pack.setdefault("assessment", {})["question_pool"] = question_pool[:12]
    base_pack["agent"] = {**prompt_info, "generation_mode": "llm_system_prompt", "review_required": True}
    return base_pack


async def build_training_material_learning_pack_with_agent(db: AsyncSession, material, target_slide_count: int) -> dict:
    """Generate learning pack through editable prompt when LLM is available; fall back to deterministic builder."""
    base_pack = build_training_material_learning_pack_payload(material=material, target_slide_count=target_slide_count)
    if base_pack.get("status") == "blocked_extraction_review_required":
        return base_pack
    material_payload = base_pack.get("material") or build_training_material_payload(material, include_internal=True)
    system_prompt, prompt_info = await get_active_training_reformatter_prompt(db)
    try:
        response_format = learning_pack_response_format(target_slide_count)
        result = await HermesAgentRuntime(hermes_runtime_config_from_env()).run_task(
            agent_id=TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
            system_prompt=system_prompt,
            task_payload={
                "task_type": "agent_generation",
                "prompt": (
                    f"{build_learning_pack_generation_user_prompt(material_payload, target_slide_count)}\n\n"
                    "Формат ответа:\n"
                    f"{json.dumps(response_format, ensure_ascii=False, indent=2)}\n\n"
                    "Отвечай ТОЛЬКО валидным JSON без markdown-блоков и пояснений."
                ),
                "max_tokens": 4500,
                "generation_options": {"temperature": 0.2},
            },
        )
        if not result.success:
            raise ValueError(
                f"Hermes generation failed "
                f"(profile={result.profile}, exit_code={result.exit_code}): "
                f"{result.error or result.output}"
            )
        raw_response = result.output
        generated = parse_structured_agent_json(raw_response)
        return merge_agent_learning_pack_payload(base_pack, generated, prompt_info)
    except Exception as error:
        base_pack["agent"] = {**prompt_info, "generation_mode": "deterministic_fallback", "ai_core_error": str(error)[:300]}
        return base_pack


def apply_learning_pack_metadata_to_material(material: ConsultantTrainingMaterial, pack: dict) -> None:
    """Persist draft practice/assessment/question pool as admin-only provenance metadata."""
    extraction = dict(material.extraction_metadata or {})
    assessment = pack.get("assessment") if isinstance(pack.get("assessment"), dict) else {}
    extraction["learning_pack"] = {
        "status": pack.get("status") or "draft_review_required",
        "review_required": True,
        "practice": pack.get("practice") or {},
        "assessment": {
            "criteria": assessment.get("criteria") or [],
            "manager_review_note": assessment.get("manager_review_note"),
            "question_pool": assessment.get("question_pool") or [],
        },
        "agent": pack.get("agent") or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    material.extraction_metadata = extraction


def user_payload(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
    }


def _normalize_seller_lookup(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace("ё", "е").split())


def _user_matches_seller_lookup(user: User, *, seller_name: str | None = None, seller_external_id: str | None = None) -> bool:
    preferences = getattr(user, "preferences", None) or {}
    if not isinstance(preferences, dict):
        preferences = {}
    external = str(seller_external_id or "").strip()
    if external:
        candidates = {
            str(preferences.get("seller_external_id") or "").strip(),
            str(preferences.get("onec_seller_id") or "").strip(),
            str(preferences.get("employee_external_id") or "").strip(),
        }
        if external in candidates:
            return True
    target = _normalize_seller_lookup(seller_name)
    if not target:
        return False
    names = [user.full_name, user.email, preferences.get("seller_name"), preferences.get("staff_name"), preferences.get("onec_seller_name")]
    for name in names:
        normalized = _normalize_seller_lookup(str(name or ""))
        if normalized and (normalized == target or normalized in target or target in normalized):
            return True
    return False


def topic_payload(topic: ConsultantTrainingTopic, *, assignments: int = 0, submitted: int = 0, accepted: int = 0) -> dict:
    return {
        "id": str(topic.id),
        "lesson_date": topic.lesson_date.isoformat() if topic.lesson_date else None,
        "title": topic.title,
        "theme": topic.theme,
        "goal": topic.goal,
        "material_text": topic.material_text,
        "assignment_text": topic.assignment_text,
        "focus_text": topic.focus_text,
        "status": topic.status,
        "approval_comment": topic.approval_comment,
        "approved_by_user_id": str(topic.approved_by_user_id) if topic.approved_by_user_id else None,
        "approved_at": iso(topic.approved_at),
        "published_at": iso(topic.published_at),
        "meta": topic.meta or {},
        "created_at": iso(topic.created_at),
        "updated_at": iso(topic.updated_at),
        "stats": {"assigned": assignments, "submitted": submitted, "accepted": accepted},
    }


def program_payload(program: ConsultantTrainingProgram) -> dict:
    return {
        "id": str(program.id),
        "code": program.code,
        "title": program.title,
        "description": program.description,
        "program_type": program.program_type,
        "status": program.status,
        "audience_rules": program.audience_rules or {},
        "is_required": bool(program.is_required),
        "order_index": program.order_index,
        "meta": program.meta or {},
        "created_at": iso(program.created_at),
        "updated_at": iso(program.updated_at),
    }


def enrollment_payload(enrollment: ConsultantTrainingEnrollment | None) -> dict | None:
    if not enrollment:
        return None
    return {
        "id": str(enrollment.id),
        "program_id": str(enrollment.program_id),
        "seller_user_id": str(enrollment.seller_user_id),
        "status": enrollment.status,
        "current_topic_id": str(enrollment.current_topic_id) if enrollment.current_topic_id else None,
        "average_score": enrollment.average_score,
        "started_at": iso(enrollment.started_at),
        "completed_at": iso(enrollment.completed_at),
        "meta": enrollment.meta or {},
    }


def module_payload(module: ConsultantTrainingModule) -> dict:
    return {
        "id": str(module.id),
        "program_id": str(module.program_id),
        "title": module.title,
        "description": module.description,
        "order_index": module.order_index,
        "meta": module.meta or {},
    }


def step_payload(step: ConsultantTrainingStep) -> dict:
    return {
        "id": str(step.id),
        "module_id": str(step.module_id),
        "title": step.title,
        "lesson_text": step.lesson_text,
        "practice_text": step.practice_text,
        "answer_template": step.answer_template,
        "assessment_rubric": step.assessment_rubric or {},
        "competencies": step.competencies or [],
        "unlock_rule": step.unlock_rule or {},
        "is_required": bool(step.is_required),
        "order_index": step.order_index,
        "meta": step.meta or {},
    }


def step_submission_payload(submission: ConsultantTrainingStepSubmission, step: ConsultantTrainingStep | None = None, *, include_internal: bool = False) -> dict:
    payload = build_step_submission_payload(submission=submission, step=step_payload(step) if step else None, include_internal=include_internal)
    payload["created_at"] = iso(submission.created_at)
    payload["reviewed_at"] = iso(submission.reviewed_at)
    payload["sent_to_consultant_at"] = iso(submission.sent_to_consultant_at)
    payload["reviewed_by_user_id"] = str(submission.reviewed_by_user_id) if submission.reviewed_by_user_id else None
    return payload


def attestation_payload(attestation: ConsultantTrainingAttestation, competency_profile: dict | None = None, *, include_internal: bool = False) -> dict:
    payload = build_attestation_payload(attestation=attestation, competency_profile=competency_profile, include_internal=include_internal)
    payload["created_at"] = iso(attestation.created_at)
    payload["submitted_at"] = iso(attestation.submitted_at)
    payload["reviewed_at"] = iso(attestation.reviewed_at)
    payload["task_payload"] = attestation.task_payload or {}
    return payload


def mentor_message_payload(message: ConsultantTrainingMentorMessage, *, include_internal: bool = False) -> dict:
    payload = build_mentor_message_payload(message, include_internal=include_internal)
    payload["created_at"] = iso(message.created_at)
    return payload


def shift_reflection_payload(reflection: ConsultantTrainingShiftReflection, seller: User | None = None, *, include_internal: bool = False) -> dict:
    payload = {
        "id": str(reflection.id),
        "seller_user_id": str(reflection.seller_user_id),
        "seller": user_payload(seller),
        "shift_date": reflection.shift_date.isoformat() if reflection.shift_date else None,
        "store_name": reflection.store_name,
        "daily_focus_snapshot": reflection.daily_focus_snapshot or {},
        "reflection_payload": reflection.reflection_payload or {},
        "ai_score": reflection.ai_score,
        "status": reflection.status,
        "seller_feedback": (reflection.ai_evaluation or {}).get("seller_feedback"),
        "manager_feedback": reflection.manager_feedback,
        "created_at": iso(reflection.created_at),
        "updated_at": iso(reflection.updated_at),
    }
    if include_internal:
        payload.update({
            "ai_evaluation": reflection.ai_evaluation or {},
            "risk_flags": reflection.risk_flags or [],
            "manager_note": reflection.manager_note,
            "reviewed_by_user_id": str(reflection.reviewed_by_user_id) if reflection.reviewed_by_user_id else None,
            "reviewed_at": iso(reflection.reviewed_at),
        })
    return payload


def coaching_action_payload(action: ConsultantTrainingCoachingAction, seller: User | None = None, *, include_internal: bool = False) -> dict:
    payload = {
        "id": str(action.id),
        "seller_user_id": str(action.seller_user_id),
        "seller": user_payload(seller),
        "reflection_id": str(action.reflection_id) if action.reflection_id else None,
        "status": action.status,
        "planned_for": action.planned_for.isoformat() if action.planned_for else None,
        "store_name": action.store_name,
        "coaching_topic": action.coaching_topic,
        "competency": action.competency,
        "kpi_metric": action.kpi_metric,
        "seller_next_step": action.seller_next_step,
        "seller_visible_feedback": action.seller_visible_feedback,
        "created_at": iso(action.created_at),
        "updated_at": iso(action.updated_at),
        "discussed_at": iso(action.discussed_at),
        "resolved_at": iso(action.resolved_at),
    }
    if include_internal:
        payload.update({
            "created_by_user_id": str(action.created_by_user_id) if action.created_by_user_id else None,
            "risk_flags": action.risk_flags or [],
            "manager_script": action.manager_script,
            "manager_result": action.manager_result,
        })
    return payload


def assignment_payload(assignment: ConsultantTrainingAssignment | None) -> dict | None:
    if not assignment:
        return None
    return {
        "id": str(assignment.id),
        "topic_id": str(assignment.topic_id),
        "seller_user_id": str(assignment.seller_user_id),
        "status": assignment.status,
        "opened_at": iso(assignment.opened_at),
        "completed_at": iso(assignment.completed_at),
    }


def submission_payload(submission: ConsultantTrainingSubmission, seller: User | None = None) -> dict:
    return {
        "id": str(submission.id),
        "topic_id": str(submission.topic_id),
        "assignment_id": str(submission.assignment_id) if submission.assignment_id else None,
        "seller_user_id": str(submission.seller_user_id),
        "seller": user_payload(seller),
        "practice_answer": submission.practice_answer,
        "evening_review": submission.evening_review,
        "ai_score": submission.ai_score,
        "ai_evaluation": submission.ai_evaluation or {},
        "review_status": submission.review_status,
        "manager_feedback": submission.manager_feedback,
        "consultant_feedback": submission.consultant_feedback,
        "reviewed_by_user_id": str(submission.reviewed_by_user_id) if submission.reviewed_by_user_id else None,
        "reviewed_at": iso(submission.reviewed_at),
        "sent_to_consultant_at": iso(submission.sent_to_consultant_at),
        "created_at": iso(submission.created_at),
    }


async def _get_topic_or_404(db: AsyncSession, topic_id: UUID) -> ConsultantTrainingTopic:
    topic = await db.get(ConsultantTrainingTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Тема обучения не найдена")
    return topic


@router.get("/admin/consultant-training/programs")
async def list_admin_programs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    programs = (await db.execute(select(ConsultantTrainingProgram).order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    return {"programs": [program_payload(program) for program in programs]}


@router.post("/admin/consultant-training/programs")
async def create_admin_program(
    payload: ProgramCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    existing = await db.scalar(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.code == payload.code))
    if existing:
        raise HTTPException(status_code=409, detail="Программа с таким кодом уже существует")
    program = ConsultantTrainingProgram(
        code=payload.code,
        title=payload.title,
        description=payload.description,
        program_type=payload.program_type,
        status=payload.status,
        audience_rules=payload.audience_rules or {},
        is_required=payload.is_required,
        order_index=payload.order_index,
        meta=payload.meta or {},
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program_payload(program)


@router.get("/admin/consultant-training/program-assignments")
async def list_admin_training_program_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    users = (await db.execute(
        select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"])).order_by(User.full_name.asc())
    )).scalars().all()
    enrollments = (await db.execute(select(ConsultantTrainingEnrollment))).scalars().all()
    by_user: dict[str, list[ConsultantTrainingEnrollment]] = {}
    for enrollment in enrollments:
        by_user.setdefault(str(enrollment.seller_user_id), []).append(enrollment)
    return {
        "users": [
            {
                **user_payload(user),
                "assigned_programs": [enrollment_payload(enrollment) for enrollment in by_user.get(str(user.id), [])],
                "active_program_id": next((str(item.program_id) for item in by_user.get(str(user.id), []) if item.status not in {"locked", "completed", "certified", "archived"}), None),
            }
            for user in users
        ]
    }


@router.post("/admin/consultant-training/program-assignments")
async def assign_admin_training_program(
    payload: TrainingProgramAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    program = await db.get(ConsultantTrainingProgram, payload.program_id)
    seller = await db.get(User, payload.seller_user_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    if not seller or seller.is_customer or seller.role not in {"seller", "manager", "admin"}:
        raise HTTPException(status_code=404, detail="Пользователь обучения не найден")
    if payload.lock_other_programs:
        other_enrollments = (await db.execute(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.seller_user_id == seller.id, ConsultantTrainingEnrollment.program_id != program.id))).scalars().all()
        for enrollment in other_enrollments:
            if enrollment.status not in {"completed", "certified"}:
                enrollment.status = "locked"
                enrollment.meta = {**(enrollment.meta or {}), "locked_by_program_assignment": str(program.id), "locked_by_user_id": str(current_user.id)}
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == seller.id))
    if not enrollment:
        enrollment = ConsultantTrainingEnrollment(program_id=program.id, seller_user_id=seller.id, status=normalize_program_status(payload.status), meta={})
        db.add(enrollment)
    enrollment.status = normalize_program_status(payload.status)
    enrollment.started_at = enrollment.started_at or datetime.now(timezone.utc)
    enrollment.meta = {**(enrollment.meta or {}), "assigned_by_user_id": str(current_user.id), "assigned_at": datetime.now(timezone.utc).isoformat(), "assignment_note": payload.note}
    await db.commit()
    await db.refresh(enrollment)
    return {"seller": user_payload(seller), "program": program_payload(program), "enrollment": enrollment_payload(enrollment), "message": "Программа назначена пользователю"}


@router.patch("/admin/consultant-training/program-assignments/{enrollment_id}/unassign")
async def unassign_admin_training_program(
    enrollment_id: UUID,
    payload: TrainingProgramUnassignRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    enrollment = await db.get(ConsultantTrainingEnrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Назначение программы не найдено")
    program = await db.get(ConsultantTrainingProgram, enrollment.program_id)
    seller = await db.get(User, enrollment.seller_user_id)
    removal = build_program_assignment_removal_payload(
        enrollment=enrollment,
        removed_by_user_id=str(current_user.id),
        note=(payload.note if payload else None),
    )
    enrollment.status = removal["status"]
    enrollment.meta = removal["meta"]
    await db.commit()
    await db.refresh(enrollment)
    return {
        "seller": user_payload(seller) if seller else None,
        "program": program_payload(program) if program else None,
        "enrollment": enrollment_payload(enrollment),
        "message": "Курс исключен из активного обучения продавца. История прохождения сохранена.",
    }


@router.get("/admin/consultant-training/programs/{program_id}/modules")
async def list_admin_program_modules(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    program = await db.get(ConsultantTrainingProgram, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    modules = (await db.execute(select(ConsultantTrainingModule).where(ConsultantTrainingModule.program_id == program_id).order_by(ConsultantTrainingModule.order_index.asc()))).scalars().all()
    steps = []
    for module in modules:
        steps.extend((await db.execute(select(ConsultantTrainingStep).where(ConsultantTrainingStep.module_id == module.id).order_by(ConsultantTrainingStep.order_index.asc()))).scalars().all())
    return build_program_structure_payload(program=program_payload(program), modules=[module_payload(module) for module in modules], steps=[step_payload(step) for step in steps])


@router.post("/admin/consultant-training/modules")
async def create_admin_module(
    payload: ModuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    if not await db.get(ConsultantTrainingProgram, payload.program_id):
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    module = ConsultantTrainingModule(program_id=payload.program_id, title=payload.title, description=payload.description, order_index=payload.order_index, meta=payload.meta or {})
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module_payload(module)


@router.post("/admin/consultant-training/steps")
async def create_admin_step(
    payload: StepCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    if not await db.get(ConsultantTrainingModule, payload.module_id):
        raise HTTPException(status_code=404, detail="Модуль обучения не найден")
    step = ConsultantTrainingStep(
        module_id=payload.module_id,
        title=payload.title,
        lesson_text=payload.lesson_text,
        practice_text=payload.practice_text,
        answer_template=payload.answer_template,
        assessment_rubric=payload.assessment_rubric or {},
        competencies=payload.competencies or [],
        unlock_rule=payload.unlock_rule or {},
        is_required=payload.is_required,
        order_index=payload.order_index,
        meta=payload.meta or {},
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step_payload(step)


async def _seller_program_cards(db: AsyncSession, current_user: User) -> list[dict]:
    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    user_enrollments = (await db.execute(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.seller_user_id == current_user.id))).scalars().all()
    visible_enrollments = [enrollment for enrollment in user_enrollments if enrollment.status != "archived"]
    enrollment_by_program = {enrollment.program_id: enrollment for enrollment in visible_enrollments}
    has_explicit_assignment = bool(user_enrollments)
    cards: list[dict] = []
    for program in programs:
        enrollment = enrollment_by_program.get(program.id)
        if not enrollment:
            if has_explicit_assignment:
                enrollment = {"status": "locked", "meta": {"not_assigned": True}}
            else:
                initial_status = "available"
                if program.code == "stylist_academy":
                    trainee = await db.scalar(
                        select(ConsultantTrainingEnrollment)
                        .join(ConsultantTrainingProgram, ConsultantTrainingProgram.id == ConsultantTrainingEnrollment.program_id)
                        .where(
                            ConsultantTrainingProgram.code == "trainee_base",
                            ConsultantTrainingEnrollment.seller_user_id == current_user.id,
                        )
                    )
                    if trainee and trainee.status not in {"completed", "certified"}:
                        initial_status = "locked"
                enrollment = ConsultantTrainingEnrollment(program_id=program.id, seller_user_id=current_user.id, status=initial_status)
                db.add(enrollment)
                await db.flush()

        modules = (await db.execute(select(ConsultantTrainingModule).where(ConsultantTrainingModule.program_id == program.id))).scalars().all()
        steps: list[ConsultantTrainingStep] = []
        for module in modules:
            steps.extend((await db.execute(select(ConsultantTrainingStep).where(ConsultantTrainingStep.module_id == module.id))).scalars().all())
        enrollment_meta = enrollment.get("meta", {}) if isinstance(enrollment, dict) else (enrollment.meta or {})
        enrollment_status = enrollment.get("status") if isinstance(enrollment, dict) else enrollment.status
        step_progress = (enrollment_meta or {}).get("step_progress", {})
        total_steps = len(steps)
        completed_steps = sum(1 for step in steps if step_progress.get(str(step.id), {}).get("status") == "accepted")
        pending_reviews = sum(1 for step in steps if step_progress.get(str(step.id), {}).get("status") in {"submitted", "review_pending"})
        revision_count = sum(1 for step in steps if step_progress.get(str(step.id), {}).get("status") == "needs_revision")

        assignments = (await db.execute(
            select(ConsultantTrainingAssignment, ConsultantTrainingTopic)
            .join(ConsultantTrainingTopic, ConsultantTrainingTopic.id == ConsultantTrainingAssignment.topic_id)
            .where(ConsultantTrainingAssignment.seller_user_id == current_user.id)
            .order_by(ConsultantTrainingTopic.lesson_date.asc())
        )).all()
        if not total_steps:
            total_steps = len(assignments)
            completed_steps = sum(1 for assignment, _topic in assignments if assignment.status == "accepted")
            pending_reviews = sum(1 for assignment, _topic in assignments if assignment.status == "submitted")
            revision_count = sum(1 for assignment, _topic in assignments if assignment.status == "needs_revision")
        scores = (await db.execute(select(ConsultantTrainingSubmission.ai_score).where(ConsultantTrainingSubmission.seller_user_id == current_user.id, ConsultantTrainingSubmission.ai_score.is_not(None)))).scalars().all()
        average_score = round(sum(scores) / len(scores), 1) if scores else (None if isinstance(enrollment, dict) else enrollment.average_score)
        next_row = None if enrollment_status in {"locked", "archived"} else next(((assignment, topic) for assignment, topic in assignments if assignment.status in {"not_opened", "opened", "in_progress", "needs_revision"}), None)
        next_assignment = None
        if next_row:
            assignment, topic = next_row
            next_assignment = {
                "assignment_id": str(assignment.id),
                "topic_id": str(topic.id),
                "title": topic.title,
                "lesson_date": topic.lesson_date.isoformat() if topic.lesson_date else None,
                "status": assignment.status,
            }
        elif steps and enrollment_status != "locked":
            structure = build_program_structure_payload(
                program=program_payload(program),
                modules=[module_payload(module) for module in modules],
                steps=[step_payload(step) for step in steps],
                step_progress=step_progress,
            )
            if structure.get("next_step"):
                next_assignment = {**structure["next_step"], "step_id": structure["next_step"]["id"]}
        card = build_program_card_payload(
            program=program_payload(program),
            enrollment={
                **(enrollment if isinstance(enrollment, dict) else (enrollment_payload(enrollment) or {})),
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "pending_reviews": pending_reviews,
                "revision_count": revision_count,
                "average_score": average_score,
            },
            next_assignment=next_assignment,
        )
        cards.append(card)
    await db.commit()
    return cards


async def _training_subject_user(db: AsyncSession, current_user: User, seller_user_id: UUID | None = None) -> User:
    """Resolve seller whose training page is being viewed.

    Normal seller login uses current_user. Admin role preview keeps the admin
    token, so seller pages must pass seller_user_id explicitly; only managers
    can view another seller's training state this way.
    """
    if not seller_user_id or seller_user_id == current_user.id:
        return current_user
    if current_user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Недоступен просмотр обучения другого продавца")
    seller = await db.get(User, seller_user_id)
    if not seller or seller.is_customer or seller.role not in {"seller", "manager", "admin"}:
        raise HTTPException(status_code=404, detail="Пользователь обучения не найден")
    return seller


@router.get("/profile/training/programs")
async def list_seller_training_programs(
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    cards = await _seller_program_cards(db, subject_user)
    active_level = "Стажер"
    if any(card["code"] == "stylist_academy" and card["status"] in {"in_progress", "completed", "certified"} for card in cards):
        active_level = "Junior Consultant"
    return {"programs": cards, "summary": {"level": active_level, "program_count": len(cards)}}


@router.post("/profile/training/programs/{program_id}/request-access")
async def request_seller_training_program_access(
    program_id: UUID,
    payload: TrainingProgramAccessRequest | None = None,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    program = await db.get(ConsultantTrainingProgram, program_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == subject_user.id))
    meta = dict((enrollment.meta if enrollment else {}) or {})
    access_request = {
        "status": "pending",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "seller_message": (payload.message if payload else None) or "Продавец запросил допуск к программе через AI-наставника",
        "program_id": str(program.id),
        "program_title": program.title,
    }
    meta["access_request"] = access_request
    if not enrollment:
        enrollment = ConsultantTrainingEnrollment(program_id=program.id, seller_user_id=subject_user.id, status="access_requested", meta=meta)
        db.add(enrollment)
    else:
        enrollment.status = "access_requested" if enrollment.status in {"locked", "archived"} or meta.get("not_assigned") else enrollment.status
        enrollment.meta = meta
    await db.commit()
    cards = await _seller_program_cards(db, subject_user)
    return {"programs": cards, "message": "Запрос на допуск отправлен руководителю. AI-наставник предложит доступные открытые программы, пока заявка ожидает решения."}


@router.post("/profile/training/programs/{program_id}/subscribe")
async def subscribe_seller_training_program(
    program_id: UUID,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    program = await db.get(ConsultantTrainingProgram, program_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    meta = dict(program.meta or {})
    if not (meta.get("open_enrollment") or meta.get("free_enrollment") or meta.get("self_enrollment")):
        raise HTTPException(status_code=409, detail="Эта программа требует допуска руководителя. Отправьте запрос на допуск.")
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == subject_user.id))
    enrollment_meta = dict((enrollment.meta if enrollment else {}) or {})
    enrollment_meta.update({"self_subscribed": True, "subscribed_at": datetime.now(timezone.utc).isoformat()})
    if not enrollment:
        enrollment = ConsultantTrainingEnrollment(program_id=program.id, seller_user_id=subject_user.id, status="available", meta=enrollment_meta)
        db.add(enrollment)
    else:
        enrollment.status = "available" if enrollment.status in {"locked", "access_requested", "archived"} else enrollment.status
        enrollment.meta = enrollment_meta
    await db.commit()
    cards = await _seller_program_cards(db, subject_user)
    return {"programs": cards, "message": f"Вы подписались на программу «{program.title}». AI-наставник может открыть первый доступный шаг."}


@router.get("/profile/training/programs/{program_id}")
async def get_seller_training_program(
    program_id: UUID,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    program = await db.get(ConsultantTrainingProgram, program_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == subject_user.id))
    if enrollment and enrollment.status == "archived":
        raise HTTPException(status_code=404, detail="Эта программа не назначена продавцу")
    if not enrollment:
        has_any_assignment = await db.scalar(select(ConsultantTrainingEnrollment.id).where(ConsultantTrainingEnrollment.seller_user_id == subject_user.id).limit(1))
        if has_any_assignment:
            raise HTTPException(status_code=404, detail="Эта программа не назначена продавцу")
        enrollment = ConsultantTrainingEnrollment(program_id=program.id, seller_user_id=subject_user.id, status="available")
        db.add(enrollment)
        await db.flush()
    modules = (await db.execute(select(ConsultantTrainingModule).where(ConsultantTrainingModule.program_id == program.id).order_by(ConsultantTrainingModule.order_index.asc()))).scalars().all()
    steps: list[ConsultantTrainingStep] = []
    for module in modules:
        steps.extend((await db.execute(select(ConsultantTrainingStep).where(ConsultantTrainingStep.module_id == module.id).order_by(ConsultantTrainingStep.order_index.asc()))).scalars().all())
    step_progress = (enrollment.meta or {}).get("step_progress", {})
    await db.commit()
    return build_program_structure_payload(
        program=program_payload(program),
        modules=[module_payload(module) for module in modules],
        steps=[step_payload(step) for step in steps],
        step_progress=step_progress,
    )


async def _get_program_step_or_404(db: AsyncSession, program_id: UUID, step_id: UUID) -> tuple[ConsultantTrainingProgram, ConsultantTrainingStep]:
    program = await db.get(ConsultantTrainingProgram, program_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    step = await db.get(ConsultantTrainingStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Этап обучения не найден")
    module = await db.get(ConsultantTrainingModule, step.module_id)
    if not module or module.program_id != program.id:
        raise HTTPException(status_code=404, detail="Этап не относится к выбранной программе")
    return program, step


async def _get_or_create_enrollment(db: AsyncSession, program_id: UUID, seller_user_id: UUID) -> ConsultantTrainingEnrollment:
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program_id, ConsultantTrainingEnrollment.seller_user_id == seller_user_id))
    if not enrollment:
        enrollment = ConsultantTrainingEnrollment(program_id=program_id, seller_user_id=seller_user_id, status="available")
        db.add(enrollment)
        await db.flush()
    return enrollment


async def _step_material_practice_gate(db: AsyncSession, *, step_id: UUID, seller_user_id: UUID) -> dict:
    links = (await db.execute(
        select(ConsultantTrainingStepMaterial)
        .where(ConsultantTrainingStepMaterial.step_id == step_id)
        .order_by(ConsultantTrainingStepMaterial.order_index.asc())
    )).scalars().all()
    material_ids = [link.material_id for link in links]
    materials = (await db.execute(
        select(ConsultantTrainingMaterial).where(
            ConsultantTrainingMaterial.id.in_(material_ids),
            ConsultantTrainingMaterial.status == "published",
        )
    )).scalars().all() if material_ids else []
    material_by_id = {material.id: material for material in materials}
    visible_links = [build_step_material_link_payload(link, material=material_by_id.get(link.material_id), include_internal=False) for link in links if material_by_id.get(link.material_id)]
    material_progress: dict[str, dict] = {}
    for material in materials:
        slides = (await db.execute(
            select(ConsultantTrainingMaterialSlide)
            .where(ConsultantTrainingMaterialSlide.material_id == material.id)
            .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
        )).scalars().all()
        progress_records = (await db.execute(
            select(ConsultantTrainingMaterialSlideProgress).where(
                ConsultantTrainingMaterialSlideProgress.material_id == material.id,
                ConsultantTrainingMaterialSlideProgress.seller_user_id == seller_user_id,
            )
        )).scalars().all()
        material_progress[str(material.id)] = build_training_material_slides_progress_payload(slides=slides, progress_records=progress_records, seller_safe=True)["summary"]
    return build_step_material_practice_gate_payload(step_materials=visible_links, material_progress=material_progress)


@router.post("/profile/training/programs/{program_id}/steps/{step_id}/submit")
async def submit_seller_training_step(
    program_id: UUID,
    step_id: UUID,
    payload: StepSubmissionCreateRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    program, step = await _get_program_step_or_404(db, program_id, step_id)
    enrollment = await _get_or_create_enrollment(db, program.id, subject_user.id)
    if enrollment.status == "locked":
        raise HTTPException(status_code=409, detail="Программа пока недоступна")

    modules = (await db.execute(select(ConsultantTrainingModule).where(ConsultantTrainingModule.program_id == program.id).order_by(ConsultantTrainingModule.order_index.asc()))).scalars().all()
    steps: list[ConsultantTrainingStep] = []
    for module in modules:
        steps.extend((await db.execute(select(ConsultantTrainingStep).where(ConsultantTrainingStep.module_id == module.id).order_by(ConsultantTrainingStep.order_index.asc()))).scalars().all())
    structure = build_program_structure_payload(
        program=program_payload(program),
        modules=[module_payload(module) for module in modules],
        steps=[step_payload(item) for item in steps],
        step_progress=(enrollment.meta or {}).get("step_progress", {}),
    )
    step_status = None
    for module in structure["modules"]:
        for item in module["steps"]:
            if item["id"] == str(step.id):
                step_status = item["status"]
                break
    if step_status == "locked":
        raise HTTPException(status_code=409, detail="Сначала завершите предыдущий обязательный этап")
    practice_gate = await _step_material_practice_gate(db, step_id=step.id, seller_user_id=subject_user.id)
    if not practice_gate.get("can_start_practice"):
        raise HTTPException(status_code=409, detail={"message": "Сначала изучите обязательные слайды материала", "practice_gate": practice_gate})

    voice_metadata = build_voice_answer_metadata(payload.voice_answer, current_user=current_user)
    answer_text = build_answer_text_with_voice(payload.practice_answer, voice_metadata)
    evaluation = evaluate_submission_quality(answer_text, expected_focus=step.practice_text or step.title)
    evaluation = attach_voice_metadata_to_evaluation(evaluation, voice_metadata)
    review_status = "revision_draft" if should_request_revision(evaluation) else "review_pending"
    submission = ConsultantTrainingStepSubmission(
        program_id=program.id,
        step_id=step.id,
        enrollment_id=enrollment.id,
        seller_user_id=subject_user.id,
        practice_answer=answer_text,
        evening_review=payload.evening_review,
        ai_score=evaluation.get("score"),
        ai_evaluation=evaluation,
        review_status=review_status,
    )
    db.add(submission)
    await db.flush()
    enrollment.status = "needs_revision" if review_status == "revision_draft" else "waiting_review"
    enrollment.meta = apply_step_submission_progress(
        current_meta=enrollment.meta or {},
        step_id=str(step.id),
        submission_id=str(submission.id),
        review_status=review_status,
        ai_score=submission.ai_score,
    )
    await db.commit()
    await db.refresh(submission)
    return {"submission": step_submission_payload(submission, step, include_internal=False), "note": "Ответ отправлен. Обратная связь появится после проверки руководителем."}


@router.get("/admin/consultant-training/step-submissions")
async def list_admin_step_submissions(
    review_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingStepSubmission, ConsultantTrainingStep, User).join(ConsultantTrainingStep, ConsultantTrainingStep.id == ConsultantTrainingStepSubmission.step_id).join(User, User.id == ConsultantTrainingStepSubmission.seller_user_id).order_by(desc(ConsultantTrainingStepSubmission.created_at))
    if review_status:
        query = query.where(ConsultantTrainingStepSubmission.review_status == normalize_step_submission_status(review_status))
    rows = (await db.execute(query)).all()
    return {"submissions": [{**step_submission_payload(submission, step, include_internal=True), "seller": user_payload(seller)} for submission, step, seller in rows]}


@router.patch("/admin/consultant-training/step-submissions/{submission_id}/review")
async def review_admin_step_submission(
    submission_id: UUID,
    payload: StepSubmissionReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    submission = await db.get(ConsultantTrainingStepSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Ответ по этапу не найден")
    step = await db.get(ConsultantTrainingStep, submission.step_id)
    review_status = normalize_step_submission_status(payload.review_status)
    if payload.send_to_consultant:
        review_status = "sent_to_consultant"
        submission.sent_to_consultant_at = datetime.now(timezone.utc)
    submission.review_status = review_status
    submission.manager_feedback = payload.manager_feedback
    submission.consultant_feedback = payload.consultant_feedback
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = datetime.now(timezone.utc)
    enrollment = await db.get(ConsultantTrainingEnrollment, submission.enrollment_id) if submission.enrollment_id else None
    if enrollment:
        enrollment.meta = apply_step_submission_progress(
            current_meta=enrollment.meta or {},
            step_id=str(submission.step_id),
            submission_id=str(submission.id),
            review_status=review_status,
            ai_score=submission.ai_score,
        )
        if review_status in {"accepted", "sent_to_consultant"}:
            enrollment.status = "in_progress"
        elif review_status in {"revision_requested", "revision_draft"}:
            enrollment.status = "needs_revision"
        else:
            enrollment.status = "waiting_review"
    await db.commit()
    await db.refresh(submission)
    return step_submission_payload(submission, step, include_internal=True)


async def _program_steps(db: AsyncSession, program_id: UUID) -> list[ConsultantTrainingStep]:
    modules = (await db.execute(select(ConsultantTrainingModule).where(ConsultantTrainingModule.program_id == program_id).order_by(ConsultantTrainingModule.order_index.asc()))).scalars().all()
    steps: list[ConsultantTrainingStep] = []
    for module in modules:
        steps.extend((await db.execute(select(ConsultantTrainingStep).where(ConsultantTrainingStep.module_id == module.id).order_by(ConsultantTrainingStep.order_index.asc()))).scalars().all())
    return steps


@router.get("/profile/training/competencies")
async def get_seller_training_competencies(
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    all_steps: list[ConsultantTrainingStep] = []
    combined_progress: dict[str, dict] = {}
    program_profiles = []
    for program in programs:
        steps = await _program_steps(db, program.id)
        enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == subject_user.id))
        step_progress = (enrollment.meta or {}).get("step_progress", {}) if enrollment else {}
        profile = build_competency_profile_payload(steps=[step_payload(step) for step in steps], step_progress=step_progress)
        program_profiles.append({"program": program_payload(program), "profile": profile})
        all_steps.extend(steps)
        combined_progress.update(step_progress)
    overall = build_competency_profile_payload(steps=[step_payload(step) for step in all_steps], step_progress=combined_progress)
    return {"summary": overall, "programs": program_profiles}


@router.get("/admin/consultant-training/competencies")
async def list_admin_training_competencies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active"))).scalars().all()
    steps_by_program = {program.id: await _program_steps(db, program.id) for program in programs}
    sellers = (await db.execute(select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"])).order_by(User.full_name.asc()))).scalars().all()
    seller_profiles = []
    competency_totals: dict[str, dict] = {}
    for seller in sellers:
        all_steps: list[ConsultantTrainingStep] = []
        combined_progress: dict[str, dict] = {}
        for program in programs:
            all_steps.extend(steps_by_program.get(program.id, []))
            enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == seller.id))
            if enrollment:
                combined_progress.update((enrollment.meta or {}).get("step_progress", {}))
        profile = build_competency_profile_payload(steps=[step_payload(step) for step in all_steps], step_progress=combined_progress)
        seller_profiles.append({"seller": user_payload(seller), "profile": profile})
        for code, stat in profile["competencies"].items():
            total = competency_totals.setdefault(code, {"code": code, "label": stat["label"], "accepted_steps": 0, "total_steps": 0})
            total["accepted_steps"] += stat["accepted_steps"]
            total["total_steps"] += stat["total_steps"]
    for stat in competency_totals.values():
        stat["percent"] = round((stat["accepted_steps"] / stat["total_steps"]) * 100) if stat["total_steps"] else 0
    risks = [item for item in seller_profiles if item["profile"]["completed_steps"] == 0 or item["profile"]["weakest_competencies"]]
    return {
        "sellers": seller_profiles,
        "team_competencies": sorted(competency_totals.values(), key=lambda item: (item["percent"], item["code"])),
        "risks": risks[:10],
    }


@router.get("/admin/consultant-training/career-levels")
async def get_admin_training_career_levels(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    competency_response = await list_admin_training_competencies(db=db, current_user=current_user)
    kpi_sellers: list[dict] = []
    kpi_error = None
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=current_user, month=month)
        kpi_sellers = kpi_dashboard.get("sellers", []) or []
    except Exception as exc:  # career levels must remain visible when KPI source is temporarily unavailable
        kpi_error = "KPI временно недоступен для расчета продажной части уровня"
    career_levels = build_team_career_levels_payload(
        seller_profiles=competency_response.get("sellers", []),
        kpi_sellers=kpi_sellers,
    )
    career_levels["month"] = month
    if kpi_error:
        career_levels["kpi_error"] = kpi_error
    return {"career_levels": career_levels}


async def _seller_competency_profile_for_program(db: AsyncSession, program: ConsultantTrainingProgram, seller_user_id: UUID) -> tuple[ConsultantTrainingEnrollment | None, dict]:
    steps = await _program_steps(db, program.id)
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == seller_user_id))
    step_progress = (enrollment.meta or {}).get("step_progress", {}) if enrollment else {}
    return enrollment, build_competency_profile_payload(steps=[step_payload(step) for step in steps], step_progress=step_progress)


@router.get("/profile/training/mentor/messages")
async def list_seller_mentor_messages(
    limit: int = Query(default=30, ge=1, le=100),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    messages = (await db.execute(
        select(ConsultantTrainingMentorMessage)
        .where(ConsultantTrainingMentorMessage.seller_user_id == subject_user.id)
        .order_by(desc(ConsultantTrainingMentorMessage.created_at))
        .limit(limit)
    )).scalars().all()
    return {"messages": [mentor_message_payload(message, include_internal=False) for message in messages]}


@router.post("/profile/training/mentor/ask")
async def ask_seller_training_mentor(
    payload: MentorAskRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    context = dict(payload.context or {})
    competency_profile: dict = {}
    program = await db.get(ConsultantTrainingProgram, payload.program_id) if payload.program_id else None
    if payload.program_id and not program:
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    if program:
        context.setdefault("program_id", str(program.id))
        context.setdefault("program_title", program.title)
        _enrollment, competency_profile = await _seller_competency_profile_for_program(db, program, subject_user.id)
    if payload.step_id:
        step = await db.get(ConsultantTrainingStep, payload.step_id)
        if not step:
            raise HTTPException(status_code=404, detail="Этап обучения не найден")
        context.setdefault("step_id", str(step.id))
        context.setdefault("step_title", step.title)
    materials = (await db.execute(
        select(ConsultantTrainingMaterial)
        .where(ConsultantTrainingMaterial.status == "published")
        .order_by(ConsultantTrainingMaterial.topic.asc(), ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.title.asc())
    )).scalars().all()
    weakest = competency_profile.get("weakest_competencies") or []
    competency = None
    if weakest and isinstance(weakest[0], dict):
        competency = weakest[0].get("label") or weakest[0].get("code")
    library_context = build_training_material_context_payload(
        materials,
        query=payload.question,
        competency=competency or context.get("step_title"),
        topic=context.get("topic") or context.get("material_topic"),
        max_materials=3,
        max_chars=1400,
    )
    reply = build_mentor_reply_with_library_context(question=payload.question, context=context, competency_profile=competency_profile, library_context=library_context)
    message = ConsultantTrainingMentorMessage(
        seller_user_id=subject_user.id,
        program_id=payload.program_id,
        step_id=payload.step_id,
        sender_role="mentor",
        question_text=payload.question,
        response_text=reply["response_text"],
        context={**reply.get("context", {}), "focus_tags": reply.get("focus_tags", [])},
        risk_flags=reply.get("risk_flags", []),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return {
        "message": mentor_message_payload(message, include_internal=False),
        "requires_manager_review": reply.get("requires_manager_review", False),
        "source_materials": reply.get("source_materials", []),
    }


@router.get("/admin/consultant-training/mentor/messages")
async def list_admin_mentor_messages(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    rows = (await db.execute(
        select(ConsultantTrainingMentorMessage, User)
        .join(User, User.id == ConsultantTrainingMentorMessage.seller_user_id)
        .order_by(desc(ConsultantTrainingMentorMessage.created_at))
        .limit(limit)
    )).all()
    return {"messages": [{**mentor_message_payload(message, include_internal=True), "seller": user_payload(seller)} for message, seller in rows]}


def _kpi_row_matches_user(row: dict, user: User) -> bool:
    preferences = user.preferences or {}
    if not isinstance(preferences, dict):
        preferences = {}
    row_external = str(row.get("seller_external_id") or row.get("external_id") or "").strip()
    user_external_ids = {
        str(preferences.get("seller_external_id") or "").strip(),
        str(preferences.get("onec_seller_id") or "").strip(),
        str(preferences.get("employee_external_id") or "").strip(),
    }
    if row_external and row_external in user_external_ids:
        return True
    row_name = _normalize_seller_lookup(row.get("seller_name") or row.get("name"))
    if not row_name or row_name in {"без имени", "unknown", "none"}:
        return False
    candidate_names = [user.full_name, user.email, preferences.get("seller_name"), preferences.get("staff_name"), preferences.get("onec_seller_name")]
    return any(
        normalized and (normalized == row_name or normalized in row_name or row_name in normalized)
        for normalized in [_normalize_seller_lookup(str(value or "")) for value in candidate_names]
    )


async def _seller_training_summary_for_user(db: AsyncSession, seller: User, *, kpi: dict | None = None) -> tuple[dict, list[dict]]:
    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    user_enrollments = (await db.execute(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.seller_user_id == seller.id))).scalars().all()
    visible_enrollments = [enrollment for enrollment in user_enrollments if enrollment.status != "archived"]
    enrollment_by_program = {enrollment.program_id: enrollment for enrollment in visible_enrollments}
    has_explicit_assignment = bool(user_enrollments)
    all_steps: list[ConsultantTrainingStep] = []
    combined_progress: dict[str, dict] = {}
    program_cards: list[dict] = []
    for program in programs:
        steps = await _program_steps(db, program.id)
        all_steps.extend(steps)
        enrollment = enrollment_by_program.get(program.id)
        virtual_enrollment = None
        if not enrollment:
            virtual_enrollment = {"status": "locked" if has_explicit_assignment else ("locked" if program.code == "stylist_academy" else "available"), "meta": {"not_assigned": has_explicit_assignment}}
        enrollment_data = enrollment_payload(enrollment) if enrollment else virtual_enrollment
        step_progress = (enrollment.meta or {}).get("step_progress", {}) if enrollment else {}
        combined_progress.update(step_progress)
        structure = build_program_structure_payload(program=program_payload(program), modules=[], steps=[step_payload(step) for step in steps], step_progress=step_progress)
        next_assignment = None if (enrollment_data or {}).get("status") in {"locked", "archived"} else structure.get("next_step")
        card = build_program_card_payload(
            program=program_payload(program),
            enrollment={
                **(enrollment_data or {}),
                "completed_steps": structure["progress"].get("completed_steps", 0),
                "total_steps": structure["progress"].get("total_steps", 0),
                "pending_reviews": 0,
                "revision_count": 0,
            },
            next_assignment=next_assignment,
        )
        program_cards.append(card)
    profile = build_competency_profile_payload(steps=[step_payload(step) for step in all_steps], step_progress=combined_progress)
    return build_personal_training_kpi_summary_payload(seller=user_payload(seller), training_profile=profile, program_cards=program_cards, kpi=kpi or {}), program_cards


async def _training_material_library_response(db: AsyncSession, materials: list[ConsultantTrainingMaterial], *, seller_view: bool = False) -> dict:
    payload = build_training_material_library_payload(materials, seller_view=seller_view)
    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    material_items = payload.get("materials") or []
    folders = []
    for program in programs:
        items = [item for item in material_items if item.get("program_code") == program.code]
        folders.append({"program": program_payload(program), "program_code": program.code, "title": program.title, "count": len(items), "materials": items})
    unassigned = [item for item in material_items if not item.get("program_code") or item.get("program_code") not in {program.code for program in programs}]
    if unassigned:
        folders.append({"program": None, "program_code": None, "title": "Без программы", "count": len(unassigned), "materials": unassigned})
    payload["program_folders"] = folders
    payload["summary"] = {**(payload.get("summary") or {}), "program_folder_count": len(folders)}
    return payload


@router.get("/admin/consultant-training/materials")
async def list_admin_training_materials(
    topic: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingMaterial).order_by(ConsultantTrainingMaterial.topic.asc(), ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.title.asc())
    if topic:
        query = query.where(ConsultantTrainingMaterial.topic == topic)
    if category:
        query = query.where(ConsultantTrainingMaterial.category == category)
    if status:
        query = query.where(ConsultantTrainingMaterial.status == normalize_training_material_status(status))
    materials = (await db.execute(query)).scalars().all()
    if q:
        return build_training_material_search_payload(materials, query=q, topic=topic, category=category, seller_view=False)
    return await _training_material_library_response(db, materials, seller_view=False)


async def _admin_training_material_progress_analytics_payload(db: AsyncSession) -> dict:
    materials = (await db.execute(select(ConsultantTrainingMaterial))).scalars().all()
    slides = (await db.execute(select(ConsultantTrainingMaterialSlide))).scalars().all()
    progress_records = (await db.execute(select(ConsultantTrainingMaterialSlideProgress))).scalars().all()
    links = (await db.execute(select(ConsultantTrainingStepMaterial))).scalars().all()
    programs = (await db.execute(select(ConsultantTrainingProgram).order_by(ConsultantTrainingProgram.order_index.asc(), ConsultantTrainingProgram.title.asc()))).scalars().all()
    enrollments = (await db.execute(select(ConsultantTrainingEnrollment))).scalars().all()
    step_submissions = (await db.execute(select(ConsultantTrainingStepSubmission))).scalars().all()
    sellers = (await db.execute(
        select(User).where(
            User.is_customer.is_(False),
            User.role.in_(["seller", "manager", "admin"]),
        )
    )).scalars().all()
    return build_training_material_progress_analytics_payload(
        materials=materials,
        slides=slides,
        progress_records=progress_records,
        sellers=sellers,
        step_material_links=links,
        programs=programs,
        enrollments=enrollments,
        step_submissions=step_submissions,
    )


@router.get("/admin/consultant-training/material-progress-analytics")
async def get_admin_training_material_progress_analytics_safe_route(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    return await _admin_training_material_progress_analytics_payload(db)


@router.get("/admin/consultant-training/materials/analytics")
async def get_admin_training_material_progress_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    return await _admin_training_material_progress_analytics_payload(db)


@router.get("/admin/consultant-training/materials/mentor-context")
async def get_admin_training_material_mentor_context(
    q: str | None = Query(default=None, min_length=1),
    competency: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    max_materials: int = Query(default=3, ge=1, le=8),
    max_chars: int = Query(default=1200, ge=120, le=6000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingMaterial).where(ConsultantTrainingMaterial.status == "published").order_by(ConsultantTrainingMaterial.topic.asc(), ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.title.asc())
    if topic:
        query = query.where(ConsultantTrainingMaterial.topic == topic)
    materials = (await db.execute(query)).scalars().all()
    return build_training_material_context_payload(materials, query=q, competency=competency, topic=topic, max_materials=max_materials, max_chars=max_chars)


@router.post("/admin/consultant-training/materials")
async def create_admin_training_material(
    payload: TrainingMaterialCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    status = normalize_training_material_status(payload.status)
    material = ConsultantTrainingMaterial(
        title=payload.title,
        topic=payload.topic or "Общее",
        category=payload.category or "Библиотека GLAME",
        description=payload.description,
        markdown_content=payload.markdown_content,
        status=status,
        tags=payload.tags or [],
        source_type=payload.source_type or "manual_md",
        extraction_metadata={},
        program_code=payload.program_code,
        competencies=payload.competencies or [],
        internal_notes=payload.internal_notes,
        created_by_user_id=current_user.id,
        approved_by_user_id=current_user.id if status == "published" else None,
        approved_at=datetime.now(timezone.utc) if status == "published" else None,
        order_index=payload.order_index,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return {"material": build_training_material_payload(material, include_internal=True), "message": "Учебный материал сохранен"}


@router.post("/admin/consultant-training/materials/import-md")
@router.post("/admin/consultant-training/materials/import-documents")
async def import_admin_training_materials_documents(
    payload: TrainingMaterialBulkImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    import_payload = build_training_material_bulk_import_payload(
        files=[item.model_dump() for item in payload.files],
        default_topic=payload.default_topic,
        default_category=payload.default_category,
        default_status=payload.default_status,
        default_program_code=payload.default_program_code,
    )
    def _sanitize_import_material(item: dict) -> dict:
        sanitized = dict(item)
        extraction = dict(sanitized.get("extraction_metadata") or sanitized.get("extraction") or {})
        if extraction.get("source_file"):
            extraction["source_file"] = build_training_material_source_file_payload(extraction, include_content=False)
        if extraction.get("visual_assets"):
            extraction["visual_assets"] = build_training_material_visual_assets_payload(extraction, include_content=False)
        sanitized["extraction"] = extraction
        sanitized["extraction_metadata"] = extraction
        return sanitized
    sanitized_import_payload = {**import_payload, "materials": [_sanitize_import_material(item) for item in import_payload.get("materials", [])]}
    if payload.dry_run:
        return {**sanitized_import_payload, "dry_run": True, "created": []}

    created = []
    created_ids = []
    for item in import_payload["materials"]:
        status = normalize_training_material_status(item.get("status"))
        material_id = uuid4()
        material = ConsultantTrainingMaterial(
            id=material_id,
            title=item["title"],
            topic=item.get("topic") or payload.default_topic,
            category=item.get("category") or payload.default_category,
            description=item.get("description"),
            markdown_content=item["markdown_content"],
            status=status,
            tags=item.get("tags") or [],
            source_type=item.get("source_type") or "md_import",
            extraction_metadata=item.get("extraction_metadata") or item.get("extraction") or {},
            program_code=item.get("program_code"),
            competencies=item.get("competencies") or [],
            internal_notes=item.get("internal_notes"),
            created_by_user_id=current_user.id,
            approved_by_user_id=current_user.id if status == "published" else None,
            approved_at=datetime.now(timezone.utc) if status == "published" else None,
            order_index=item.get("order_index") or 100,
        )
        db.add(material)
        created.append(material)
        created_ids.append(material_id)
    await db.commit()
    auto_generated_slides = 0
    for material in created:
        await db.refresh(material)
        if payload.auto_generate_learning_pack:
            pack = await build_training_material_learning_pack_with_agent(db, material, target_slide_count=5)
            if pack.get("status") != "blocked_extraction_review_required":
                for slide_payload in pack.get("slides") or []:
                    slide = ConsultantTrainingMaterialSlide(
                        material_id=material.id,
                        title=slide_payload["title"],
                        body=slide_payload.get("body"),
                        image_url=slide_payload.get("image_url"),
                        image_prompt=slide_payload.get("image_prompt"),
                        speaker_note=slide_payload.get("speaker_note"),
                        quiz_question=slide_payload.get("quiz_question"),
                        status="draft",
                        order_index=slide_payload.get("order_index") or 100,
                        meta={**(slide_payload.get("meta") or {}), "generated_from": "import_agent", "review_required": True},
                    )
                    db.add(slide)
                    auto_generated_slides += 1
                apply_learning_pack_metadata_to_material(material, pack)
                material.internal_notes = ((material.internal_notes or "") + "\n\nАгент автоматически сформировал draft-слайды и пул проверочных вопросов из исходника; требуется проверка руководителя перед публикацией.").strip()
    if auto_generated_slides:
        await db.commit()
        for material in created:
            await db.refresh(material)
    refreshed_created = []
    if created_ids:
        refreshed_created = (await db.execute(
            select(ConsultantTrainingMaterial)
            .where(ConsultantTrainingMaterial.id.in_(created_ids))
            .order_by(ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.created_at.asc())
        )).scalars().all()
    return {
        **sanitized_import_payload,
        "dry_run": False,
        "created": [build_training_material_payload(material, include_internal=True) for material in refreshed_created],
        "auto_generated_slides": auto_generated_slides,
        "message": f"Импортировано материалов: {len(created)}" + (f" · AI-слайдов: {auto_generated_slides}" if auto_generated_slides else ""),
    }


@router.get("/admin/consultant-training/materials/{material_id}/slides")
async def list_admin_training_material_slides(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    slides = (await db.execute(
        select(ConsultantTrainingMaterialSlide)
        .where(ConsultantTrainingMaterialSlide.material_id == material_id)
        .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
    )).scalars().all()
    return {"material": build_training_material_payload(material, include_internal=True), **build_training_material_slides_payload(slides, seller_safe=False)}


@router.post("/admin/consultant-training/materials/{material_id}/slides")
async def create_admin_training_material_slide(
    material_id: UUID,
    payload: TrainingMaterialSlideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    slide = ConsultantTrainingMaterialSlide(
        material_id=material_id,
        title=payload.title,
        body=payload.body,
        image_url=payload.image_url,
        image_prompt=payload.image_prompt,
        speaker_note=payload.speaker_note,
        quiz_question=payload.quiz_question,
        status=normalize_training_material_status(payload.status),
        order_index=payload.order_index,
        meta=payload.meta or {},
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return {"slide": build_training_material_slide_payload(slide, include_internal=True), "message": "Слайд добавлен"}


@router.patch("/admin/consultant-training/materials/{material_id}/slides/{slide_id}")
async def update_admin_training_material_slide(
    material_id: UUID,
    slide_id: UUID,
    payload: TrainingMaterialSlideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    slide = await db.get(ConsultantTrainingMaterialSlide, slide_id)
    if not slide or slide.material_id != material_id:
        raise HTTPException(status_code=404, detail="Слайд не найден")
    slide.title = payload.title
    slide.body = payload.body
    slide.image_url = payload.image_url
    slide.image_prompt = payload.image_prompt
    slide.speaker_note = payload.speaker_note
    slide.quiz_question = payload.quiz_question
    slide.status = normalize_training_material_status(payload.status)
    slide.order_index = payload.order_index
    slide.meta = payload.meta or {}
    await db.commit()
    await db.refresh(slide)
    return {"slide": build_training_material_slide_payload(slide, include_internal=True), "message": "Слайд обновлен"}


@router.delete("/admin/consultant-training/materials/{material_id}/slides/{slide_id}")
async def delete_admin_training_material_slide(
    material_id: UUID,
    slide_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    slide = await db.get(ConsultantTrainingMaterialSlide, slide_id)
    if not slide or slide.material_id != material_id:
        raise HTTPException(status_code=404, detail="Слайд не найден")
    await db.delete(slide)
    await db.commit()
    return {"message": "Слайд удален"}


@router.post("/admin/consultant-training/materials/{material_id}/learning-pack")
async def generate_admin_training_material_learning_pack(
    material_id: UUID,
    payload: TrainingMaterialLearningPackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    pack = await build_training_material_learning_pack_with_agent(db, material, target_slide_count=payload.target_slide_count)
    if pack.get("status") == "blocked_extraction_review_required":
        return pack
    created_slides = []
    if payload.apply:
        if payload.replace_all_slides:
            existing_slides = (await db.execute(select(ConsultantTrainingMaterialSlide).where(
                ConsultantTrainingMaterialSlide.material_id == material_id,
            ))).scalars().all()
            for existing_slide in existing_slides:
                await db.delete(existing_slide)
        elif payload.replace_existing_draft_slides:
            existing_drafts = (await db.execute(select(ConsultantTrainingMaterialSlide).where(
                ConsultantTrainingMaterialSlide.material_id == material_id,
                ConsultantTrainingMaterialSlide.status == "draft",
            ))).scalars().all()
            for draft_slide in existing_drafts:
                await db.delete(draft_slide)
        for slide_payload in pack["slides"]:
            slide = ConsultantTrainingMaterialSlide(
                material_id=material_id,
                title=slide_payload["title"],
                body=slide_payload.get("body"),
                image_url=slide_payload.get("image_url"),
                image_prompt=slide_payload.get("image_prompt"),
                speaker_note=slide_payload.get("speaker_note"),
                quiz_question=slide_payload.get("quiz_question"),
                status="draft",
                order_index=slide_payload.get("order_index") or 100,
                meta={**(slide_payload.get("meta") or {}), "generated_from": "learning_pack", "review_required": True},
            )
            db.add(slide)
            created_slides.append(slide)
        apply_learning_pack_metadata_to_material(material, pack)
        material.internal_notes = ((material.internal_notes or "") + "\n\nAI learning pack draft сформирован: слайды, практика и пул проверочных вопросов; требуется проверка руководителя перед публикацией.").strip()
        await db.commit()
        for slide in created_slides:
            await db.refresh(slide)
        pack["created_slides"] = [build_training_material_slide_payload(slide, include_internal=True) for slide in created_slides]
        pack["message"] = f"Сформирован draft learning pack: {len(created_slides)} слайдов. Проверьте перед публикацией."
    else:
        pack["created_slides"] = []
        pack["message"] = "Предпросмотр learning pack готов. Слайды еще не сохранены."
    return pack


@router.delete("/admin/consultant-training/materials/{material_id}")
async def delete_admin_training_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    summary = {
        "slides": (await db.execute(select(func.count()).select_from(ConsultantTrainingMaterialSlide).where(ConsultantTrainingMaterialSlide.material_id == material_id))).scalar() or 0,
        "slide_progress": (await db.execute(select(func.count()).select_from(ConsultantTrainingMaterialSlideProgress).where(ConsultantTrainingMaterialSlideProgress.material_id == material_id))).scalar() or 0,
        "step_links": (await db.execute(select(func.count()).select_from(ConsultantTrainingStepMaterial).where(ConsultantTrainingStepMaterial.material_id == material_id))).scalar() or 0,
        "status_history": (await db.execute(select(func.count()).select_from(ConsultantTrainingMaterialStatusHistory).where(ConsultantTrainingMaterialStatusHistory.material_id == material_id))).scalar() or 0,
    }
    deleted_title = material.title
    await db.delete(material)
    await db.commit()
    return {"message": "Учебный материал полностью удален", "deleted_material_id": str(material_id), "deleted_title": deleted_title, "deleted_related": summary}


@router.get("/admin/consultant-training/materials/{material_id}")
async def get_admin_training_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    history = (await db.execute(
        select(ConsultantTrainingMaterialStatusHistory)
        .where(ConsultantTrainingMaterialStatusHistory.material_id == material.id)
        .order_by(desc(ConsultantTrainingMaterialStatusHistory.created_at))
    )).scalars().all()
    return build_training_material_detail_payload(material, history=history)


@router.get("/admin/consultant-training/materials/{material_id}/visual-assets")
async def list_admin_training_material_visual_assets(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    assets = build_training_material_visual_assets_payload(material.extraction_metadata or {}, include_content=True)
    return {
        "material": build_training_material_payload(material, include_internal=True),
        "visual_assets": assets,
        "summary": (material.extraction_metadata or {}).get("visual_assets_summary") or {
            "total": len(assets),
            "pending_review": len([asset for asset in assets if asset.get("status") == "pending_review"]),
            "approved": len([asset for asset in assets if asset.get("status") == "approved"]),
            "rejected": len([asset for asset in assets if asset.get("status") == "rejected"]),
            "attached": len([asset for asset in assets if asset.get("attached_slide_id")]),
        },
    }


@router.post("/admin/consultant-training/materials/{material_id}/visual-assets/attach-all")
async def attach_all_admin_training_material_visual_assets(
    material_id: UUID,
    payload: TrainingMaterialVisualAssetsAttachAllRequest = TrainingMaterialVisualAssetsAttachAllRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    extraction = dict(material.extraction_metadata or {})
    raw_assets = list(extraction.get("visual_assets") or [])
    public_assets = [asset for asset in build_training_material_visual_assets_payload(extraction, include_content=True) if asset.get("image_url") and asset.get("status") != "rejected"]
    if not public_assets:
        raise HTTPException(status_code=404, detail="Нет доступных визуальных ассетов для добавления")
    slides = (await db.execute(
        select(ConsultantTrainingMaterialSlide)
        .where(ConsultantTrainingMaterialSlide.material_id == material_id)
        .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
    )).scalars().all()
    available_slides = [slide for slide in slides if payload.replace_existing_slide_images or not slide.image_url]
    attached_count = 0
    created_count = 0
    updated_slides: list[ConsultantTrainingMaterialSlide] = []
    asset_to_slide: dict[str, str] = {}
    next_order = max([int(slide.order_index or 0) for slide in slides] or [0]) + 10
    for index, asset in enumerate(public_assets, start=1):
        slide = available_slides.pop(0) if available_slides else None
        if slide is None and payload.create_missing_slides:
            slide = ConsultantTrainingMaterialSlide(
                material_id=material_id,
                title=f"Визуальный пример {index}: {asset.get('filename') or 'из исходника'}"[:255],
                body="Визуал из исходного материала. Руководитель проверяет, как он поддерживает учебный слайд, перед публикацией продавцам.",
                status="draft",
                order_index=next_order,
                meta={"generated_from": "visual_assets_attach_all", "review_required": True},
            )
            next_order += 10
            db.add(slide)
            await db.flush()
            created_count += 1
        if slide is None:
            continue
        slide.image_url = asset["image_url"]
        slide.meta = {**(slide.meta or {}), "visual_asset_id": asset.get("asset_id"), "visual_asset_source": "admin_approved_pdf_asset", "review_required": True}
        updated_slides.append(slide)
        asset_to_slide[str(asset.get("asset_id"))] = str(slide.id)
        attached_count += 1
    now = datetime.now(timezone.utc).isoformat()
    for raw_asset in raw_assets:
        asset_id = str(raw_asset.get("asset_id") or raw_asset.get("id") or "")
        if asset_id in asset_to_slide:
            raw_asset["status"] = "attached"
            raw_asset["attached_slide_id"] = asset_to_slide[asset_id]
            raw_asset["review_note"] = payload.note
            raw_asset["reviewed_by_user_id"] = str(current_user.id)
            raw_asset["reviewed_at"] = now
    extraction["visual_assets"] = raw_assets
    summary = {"total": 0, "pending_review": 0, "approved": 0, "rejected": 0, "attached": 0}
    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue
        summary["total"] += 1
        status = asset.get("status") or "pending_review"
        if status in summary:
            summary[status] += 1
    extraction["visual_assets_summary"] = summary
    material.extraction_metadata = extraction
    await db.commit()
    await db.refresh(material)
    for slide in updated_slides:
        await db.refresh(slide)
    return {
        "material": build_training_material_payload(material, include_internal=True),
        "visual_assets": build_training_material_visual_assets_payload(material.extraction_metadata or {}, include_content=True),
        "slides": [build_training_material_slide_payload(slide, include_internal=True) for slide in updated_slides],
        "attached_count": attached_count,
        "created_slides": created_count,
        "message": f"Добавлено визуалов: {attached_count}" + (f" · создано draft-слайдов: {created_count}" if created_count else ""),
    }


@router.patch("/admin/consultant-training/materials/{material_id}/visual-assets/{asset_id}")
async def review_admin_training_material_visual_asset(
    material_id: UUID,
    asset_id: str,
    payload: TrainingMaterialVisualAssetReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    slide = None
    if payload.slide_id:
        slide = await db.get(ConsultantTrainingMaterialSlide, payload.slide_id)
        if not slide or slide.material_id != material_id:
            raise HTTPException(status_code=404, detail="Слайд не найден для этого материала")
    try:
        updated_extraction = build_training_material_visual_asset_update_payload(
            material.extraction_metadata or {},
            asset_id=asset_id,
            status=payload.status,
            note=payload.note,
            slide_id=str(payload.slide_id) if payload.slide_id else None,
            reviewed_by_user_id=str(current_user.id),
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Визуальный ассет не найден") from error
    material.extraction_metadata = updated_extraction
    selected_asset = next((asset for asset in build_training_material_visual_assets_payload(updated_extraction, include_content=True) if asset.get("asset_id") == asset_id), None)
    if slide and payload.apply_to_slide and payload.status == "approved" and selected_asset and selected_asset.get("image_url"):
        slide.image_url = selected_asset["image_url"]
        slide.meta = {**(slide.meta or {}), "visual_asset_id": asset_id, "visual_asset_source": "admin_approved_pdf_asset", "review_required": True}
    await db.commit()
    if slide:
        await db.refresh(slide)
    await db.refresh(material)
    return {
        "material": build_training_material_payload(material, include_internal=True),
        "visual_assets": build_training_material_visual_assets_payload(material.extraction_metadata or {}, include_content=True),
        "slide": build_training_material_slide_payload(slide, include_internal=True) if slide else None,
        "message": "Визуальный ассет обновлен" + (" и прикреплен к слайду" if slide and payload.apply_to_slide else ""),
    }


@router.get("/admin/consultant-training/materials/{material_id}/source-file")
async def download_admin_training_material_source_file(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    source_file = build_training_material_source_file_payload(material.extraction_metadata or {}, include_content=True)
    if not source_file or not source_file.get("content_base64"):
        raise HTTPException(status_code=404, detail="Исходный файл не сохранен для скачивания. Материал был загружен до включения хранения вложений или файл слишком большой.")
    try:
        content = base64.b64decode(str(source_file.get("content_base64") or ""))
    except Exception as error:
        raise HTTPException(status_code=500, detail="Исходный файл поврежден в metadata") from error
    filename = str(source_file.get("filename") or f"training-material-{material_id}").replace('"', "")
    ascii_filename = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_filename or ascii_filename.startswith("."):
        extension = ascii_filename if ascii_filename.startswith(".") else ""
        ascii_filename = f"training-material-{material_id}{extension}"
    encoded_filename = quote(filename)
    media_type = str(source_file.get("mime_type") or "application/octet-stream")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"},
    )


@router.patch("/admin/consultant-training/materials/{material_id}")
async def update_admin_training_material(
    material_id: UUID,
    payload: TrainingMaterialUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    for field in ["title", "topic", "category", "description", "markdown_content", "tags", "source_type", "program_code", "competencies", "internal_notes", "order_index"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(material, field, value)
    old_status = normalize_training_material_status(material.status)
    publish_cascade: dict | None = None
    if payload.status is not None:
        new_status = normalize_training_material_status(payload.status)
        gate = build_training_material_publish_gate_payload(material, target_status=new_status)
        if not gate.get("can_publish"):
            raise HTTPException(status_code=409, detail=gate)
        if new_status != old_status:
            change = build_training_material_status_change_payload(
                material=material,
                new_status=new_status,
                changed_by_user_id=current_user.id,
                note=payload.status_note,
            )
            db.add(ConsultantTrainingMaterialStatusHistory(
                material_id=material.id,
                from_status=change["from_status"],
                to_status=change["to_status"],
                note=change.get("note"),
                changed_by_user_id=current_user.id,
            ))
        material.status = new_status
        if material.status == "published":
            material.approved_by_user_id = current_user.id
            material.approved_at = datetime.now(timezone.utc)
            slides = (await db.execute(
                select(ConsultantTrainingMaterialSlide).where(ConsultantTrainingMaterialSlide.material_id == material_id)
            )).scalars().all()
            publish_cascade = build_training_material_publish_cascade_payload(
                material=material,
                slides=slides,
                extraction_metadata=material.extraction_metadata or {},
                reviewed_by_user_id=current_user.id,
            )
            slide_ids_to_publish = set(publish_cascade.get("slides_to_publish") or [])
            for slide in slides:
                if str(slide.id) in slide_ids_to_publish:
                    slide.status = "published"
                    slide.meta = {**(slide.meta or {}), "published_with_material": True, "published_by_user_id": str(current_user.id)}
            material.extraction_metadata = publish_cascade.get("extraction_metadata") or material.extraction_metadata or {}
    await db.commit()
    await db.refresh(material)
    message = "Учебный материал обновлен"
    if publish_cascade:
        message = f"Материал опубликован: слайдов опубликовано {publish_cascade.get('published_slides_count', 0)}, визуалов обновлено {publish_cascade.get('visual_assets_summary', {}).get('approved', 0) + publish_cascade.get('visual_assets_summary', {}).get('attached', 0)}"
    return {"material": build_training_material_payload(material, include_internal=True), "publish_cascade": publish_cascade, "message": message}


@router.get("/admin/consultant-training/document-extractors/status")
async def get_admin_training_document_extractors_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    return build_document_extractor_status_payload()


@router.patch("/admin/consultant-training/materials/{material_id}/retry-extraction")
async def retry_admin_training_material_extraction(
    material_id: UUID,
    payload: TrainingMaterialRetryExtractionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    try:
        imported = parse_training_material_document_import(
            filename=payload.filename,
            content=payload.content,
            content_base64=payload.content_base64,
            mime_type=payload.mime_type,
            default_topic=material.topic or "Общее",
            default_category=material.category or "Импорт документов",
            default_status="draft",
        )
        if payload.mark_reviewed:
            retry = build_training_material_retry_extraction_payload(
                material=material,
                filename=payload.filename,
                extracted_text=imported.get("markdown_content") or "",
                extractor=(imported.get("extraction") or {}).get("extractor") or "retry_extraction",
                reviewed_by_user_id=current_user.id,
                note=payload.note,
            )
            imported_source_file = (imported.get("extraction_metadata") or imported.get("extraction") or {}).get("source_file")
            if imported_source_file:
                retry.setdefault("extraction_metadata", {})["source_file"] = imported_source_file
        else:
            retry = {
                "markdown_content": imported.get("markdown_content") or material.markdown_content,
                "extraction_metadata": imported.get("extraction_metadata") or imported.get("extraction") or {},
                "internal_notes": "\n".join(part for part in [material.internal_notes, imported.get("internal_notes"), payload.note] if part),
            }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error) or "Не удалось извлечь текст") from error
    material.markdown_content = retry["markdown_content"]
    material.extraction_metadata = retry["extraction_metadata"]
    material.internal_notes = retry["internal_notes"]
    await db.commit()
    await db.refresh(material)
    return {
        "material": build_training_material_payload(material, include_internal=True),
        "publish_gate": build_training_material_publish_gate_payload(material, target_status="published"),
        "message": "Повторное извлечение применено. Проверьте Markdown перед публикацией.",
    }


@router.patch("/admin/consultant-training/materials/{material_id}/extraction-review")
async def review_admin_training_material_extraction(
    material_id: UUID,
    payload: TrainingMaterialExtractionReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    review = build_training_material_extraction_review_payload(
        material=material,
        reviewed_markdown=payload.reviewed_markdown,
        reviewed_by_user_id=current_user.id,
        note=payload.note,
    )
    material.markdown_content = review["markdown_content"]
    material.extraction_metadata = review["extraction_metadata"]
    material.internal_notes = review["internal_notes"]
    await db.commit()
    await db.refresh(material)
    return {
        "material": build_training_material_payload(material, include_internal=True),
        "publish_gate": build_training_material_publish_gate_payload(material, target_status="published"),
        "message": "Текст извлечения/OCR проверен. Материал можно отправлять на методическую проверку и публикацию.",
    }


@router.get("/admin/consultant-training/step-materials")
async def list_admin_step_material_links(
    step_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingStepMaterial).order_by(ConsultantTrainingStepMaterial.step_id.asc(), ConsultantTrainingStepMaterial.order_index.asc())
    if step_id:
        query = query.where(ConsultantTrainingStepMaterial.step_id == step_id)
    links = (await db.execute(query)).scalars().all()
    material_ids = [link.material_id for link in links]
    materials = (await db.execute(select(ConsultantTrainingMaterial).where(ConsultantTrainingMaterial.id.in_(material_ids)))).scalars().all() if material_ids else []
    material_by_id = {material.id: material for material in materials}
    return {"links": [build_step_material_link_payload(link, material=material_by_id.get(link.material_id), include_internal=True) for link in links]}


@router.post("/admin/consultant-training/step-materials")
async def create_admin_step_material_link(
    payload: StepMaterialLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    step = await db.get(ConsultantTrainingStep, payload.step_id)
    material = await db.get(ConsultantTrainingMaterial, payload.material_id)
    if not step or not material:
        raise HTTPException(status_code=404, detail="Шаг или материал не найден")
    existing = await db.scalar(select(ConsultantTrainingStepMaterial).where(
        ConsultantTrainingStepMaterial.step_id == payload.step_id,
        ConsultantTrainingStepMaterial.material_id == payload.material_id,
        ConsultantTrainingStepMaterial.role == payload.role,
    ))
    if existing:
        existing.program_id = payload.program_id
        existing.module_id = payload.module_id or step.module_id
        existing.required_to_complete = payload.required_to_complete
        existing.order_index = payload.order_index
        existing.meta = payload.meta or {}
        link = existing
    else:
        link = ConsultantTrainingStepMaterial(
            program_id=payload.program_id,
            module_id=payload.module_id or step.module_id,
            step_id=payload.step_id,
            material_id=payload.material_id,
            role=payload.role,
            required_to_complete=payload.required_to_complete,
            order_index=payload.order_index,
            meta=payload.meta or {},
        )
        db.add(link)
    await db.commit()
    await db.refresh(link)
    return {"link": build_step_material_link_payload(link, material=material, include_internal=True), "message": "Материал привязан к шагу обучения"}


async def _assigned_training_program_for_user(db: AsyncSession, seller_user_id: UUID) -> ConsultantTrainingProgram | None:
    enrollment = await db.scalar(
        select(ConsultantTrainingEnrollment)
        .join(ConsultantTrainingProgram, ConsultantTrainingProgram.id == ConsultantTrainingEnrollment.program_id)
        .where(
            ConsultantTrainingEnrollment.seller_user_id == seller_user_id,
            ConsultantTrainingProgram.status == "active",
            ConsultantTrainingEnrollment.status.in_(["available", "in_progress", "waiting_review", "needs_revision"]),
        )
        .order_by(ConsultantTrainingEnrollment.updated_at.desc().nullslast(), ConsultantTrainingEnrollment.created_at.desc())
    )
    return await db.get(ConsultantTrainingProgram, enrollment.program_id) if enrollment else None


async def _seller_step_materials_payload(db: AsyncSession, current_user: User, program_id: UUID | None = None, fallback_material: ConsultantTrainingMaterial | None = None) -> dict:
    assigned_program = None if program_id else await _assigned_training_program_for_user(db, current_user.id)
    program = await db.get(ConsultantTrainingProgram, program_id) if program_id else (assigned_program or await db.scalar(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc())))
    if not program:
        return {"summary": {"steps": 0, "unlocked_materials": 0}, "current_step": None, "steps": []}
    steps = await _program_steps(db, program.id)
    enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == current_user.id))
    step_progress = (enrollment.meta or {}).get("step_progress", {}) if enrollment else {}
    step_ids = [step.id for step in steps]
    links = (await db.execute(select(ConsultantTrainingStepMaterial).where(ConsultantTrainingStepMaterial.step_id.in_(step_ids)).order_by(ConsultantTrainingStepMaterial.order_index.asc()))).scalars().all() if step_ids else []
    material_ids = [link.material_id for link in links]
    materials = (await db.execute(select(ConsultantTrainingMaterial).where(ConsultantTrainingMaterial.id.in_(material_ids), ConsultantTrainingMaterial.status == "published"))).scalars().all() if material_ids else []
    payload = build_unlocked_step_materials_payload(steps=steps, step_material_links=links, materials=materials, step_progress=step_progress)
    if fallback_material and not payload.get("summary", {}).get("unlocked_materials") and steps:
        fallback_step = None
        for step in steps:
            raw_status = step_progress.get(str(step.id))
            status = raw_status.get("status") if isinstance(raw_status, dict) else raw_status
            status = status or "available"
            if status not in {"locked", "blocked", "accepted", "completed"}:
                fallback_step = step
                break
        fallback_step = fallback_step or steps[0]
        fallback_link = {
            "id": f"pilot-{fallback_material.id}",
            "program_id": str(program.id),
            "module_id": str(fallback_step.module_id),
            "step_id": str(fallback_step.id),
            "material_id": str(fallback_material.id),
            "role": "primary_lesson",
            "required_to_complete": True,
            "order_index": 1,
            "material": build_training_material_payload(fallback_material, include_internal=False),
            "title": fallback_material.title,
            "topic": fallback_material.topic,
            "status": fallback_material.status,
        }
        slides = (await db.execute(
            select(ConsultantTrainingMaterialSlide)
            .where(ConsultantTrainingMaterialSlide.material_id == fallback_material.id)
            .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
        )).scalars().all()
        progress_records = (await db.execute(select(ConsultantTrainingMaterialSlideProgress).where(
            ConsultantTrainingMaterialSlideProgress.material_id == fallback_material.id,
            ConsultantTrainingMaterialSlideProgress.seller_user_id == current_user.id,
        ))).scalars().all()
        progress_summary = build_training_material_slides_progress_payload(slides=slides, progress_records=progress_records, seller_safe=True)["summary"]
        current_step_payload = {
            "id": str(fallback_step.id),
            "title": fallback_material.title,
            "status": "available",
            "is_unlocked": True,
            "locked_reason": None,
            "materials": [fallback_link],
            "practice_gate": build_step_material_practice_gate_payload(step_materials=[fallback_link], material_progress={str(fallback_material.id): progress_summary}),
            "source": "single_published_material_fallback",
        }
        payload["current_step"] = current_step_payload
        payload["steps"] = [current_step_payload if item.get("id") == str(fallback_step.id) else item for item in payload.get("steps", [])]
        payload["summary"] = {**(payload.get("summary") or {}), "unlocked_materials": 1, "single_material_mode": True}
        payload["current_material"] = {**build_training_material_payload(fallback_material, include_internal=False), "progress": progress_summary, "program_id": str(program.id), "step_id": str(fallback_step.id), "step_title": fallback_material.title}
    if payload.get("current_step") and not payload["current_step"].get("practice_gate"):
        payload["current_step"]["practice_gate"] = await _step_material_practice_gate(db, step_id=UUID(payload["current_step"]["id"]), seller_user_id=current_user.id)
    if payload.get("current_step") and not payload.get("current_material"):
        current_links = payload["current_step"].get("materials") or []
        current_link = next((item for item in current_links if item.get("required_to_complete")), None) or (current_links[0] if current_links else None)
        current_material_id = current_link.get("material_id") if isinstance(current_link, dict) else None
        if current_material_id:
            material = await db.get(ConsultantTrainingMaterial, UUID(str(current_material_id)))
            if material and material.status == "published":
                slides = (await db.execute(
                    select(ConsultantTrainingMaterialSlide)
                    .where(ConsultantTrainingMaterialSlide.material_id == material.id)
                    .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
                )).scalars().all()
                progress_records = (await db.execute(select(ConsultantTrainingMaterialSlideProgress).where(
                    ConsultantTrainingMaterialSlideProgress.material_id == material.id,
                    ConsultantTrainingMaterialSlideProgress.seller_user_id == current_user.id,
                ))).scalars().all()
                progress_summary = build_training_material_slides_progress_payload(slides=slides, progress_records=progress_records, seller_safe=True)["summary"]
                payload["current_material"] = {
                    **build_training_material_payload(material, include_internal=False),
                    "progress": progress_summary,
                    "program_id": str(program.id),
                    "step_id": payload["current_step"].get("id"),
                    "step_title": payload["current_step"].get("title") or material.title,
                }
    return payload


@router.get("/profile/training/step-materials")
async def list_seller_step_materials(
    program_id: UUID | None = Query(default=None),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    return await _seller_step_materials_payload(db, subject_user, program_id=program_id)


@router.get("/profile/training/materials")
async def list_seller_training_materials(
    topic: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingMaterial).where(ConsultantTrainingMaterial.status == "published").order_by(ConsultantTrainingMaterial.topic.asc(), ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.title.asc())
    if topic:
        query = query.where(ConsultantTrainingMaterial.topic == topic)
    if category:
        query = query.where(ConsultantTrainingMaterial.category == category)
    materials = (await db.execute(query)).scalars().all()
    if q:
        return build_training_material_search_payload(materials, query=q, topic=topic, category=category, seller_view=True)
    return await _training_material_library_response(db, materials, seller_view=True)


@router.get("/profile/training/materials/{material_id}/slides")
async def get_seller_training_material_slides(
    material_id: UUID,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material or material.status != "published":
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    slides = (await db.execute(
        select(ConsultantTrainingMaterialSlide)
        .where(ConsultantTrainingMaterialSlide.material_id == material_id)
        .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
    )).scalars().all()
    progress_records = (await db.execute(
        select(ConsultantTrainingMaterialSlideProgress).where(
            ConsultantTrainingMaterialSlideProgress.material_id == material_id,
            ConsultantTrainingMaterialSlideProgress.seller_user_id == subject_user.id,
        )
    )).scalars().all()
    return {"material": build_training_material_payload(material, include_internal=False), **build_training_material_slides_progress_payload(slides=slides, progress_records=progress_records, seller_safe=True)}


@router.post("/profile/training/materials/{material_id}/slides/{slide_id}/viewed")
async def mark_seller_training_material_slide_viewed(
    material_id: UUID,
    slide_id: UUID,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    slide = await db.get(ConsultantTrainingMaterialSlide, slide_id)
    if not material or material.status != "published" or not slide or slide.material_id != material_id or slide.status != "published":
        raise HTTPException(status_code=404, detail="Слайд не найден")
    now = datetime.now(timezone.utc)
    progress = await db.scalar(select(ConsultantTrainingMaterialSlideProgress).where(
        ConsultantTrainingMaterialSlideProgress.slide_id == slide_id,
        ConsultantTrainingMaterialSlideProgress.seller_user_id == subject_user.id,
    ))
    if progress:
        progress.viewed_at = progress.viewed_at or now
        progress.completed_at = progress.completed_at or now
    else:
        progress = ConsultantTrainingMaterialSlideProgress(
            material_id=material_id,
            slide_id=slide_id,
            seller_user_id=subject_user.id,
            viewed_at=now,
            completed_at=now,
            meta={},
        )
        db.add(progress)
    await db.commit()
    progress_records = (await db.execute(
        select(ConsultantTrainingMaterialSlideProgress).where(
            ConsultantTrainingMaterialSlideProgress.material_id == material_id,
            ConsultantTrainingMaterialSlideProgress.seller_user_id == subject_user.id,
        )
    )).scalars().all()
    slides = (await db.execute(
        select(ConsultantTrainingMaterialSlide)
        .where(ConsultantTrainingMaterialSlide.material_id == material_id)
        .order_by(ConsultantTrainingMaterialSlide.order_index.asc(), ConsultantTrainingMaterialSlide.title.asc())
    )).scalars().all()
    return {"message": "Слайд отмечен как изученный", **build_training_material_slides_progress_payload(slides=slides, progress_records=progress_records, seller_safe=True)}


@router.get("/profile/training/materials/{material_id}")
async def get_seller_training_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    material = await db.get(ConsultantTrainingMaterial, material_id)
    if not material or material.status != "published":
        raise HTTPException(status_code=404, detail="Учебный материал не найден")
    return {"material": build_training_material_payload(material, include_internal=False)}


@router.post("/admin/consultant-training/personal-summary")
async def get_admin_personal_training_summary(
    payload: PersonalTrainingSummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    seller = await db.scalar(select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"]), User.email == payload.seller_name)) if payload.seller_name and "@" in payload.seller_name else None
    if not seller:
        users = (await db.execute(select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"])))).scalars().all()
        seller = next((user for user in users if _user_matches_seller_lookup(user, seller_name=payload.seller_name, seller_external_id=payload.seller_external_id)), None)
    if not seller:
        return {
            "found": False,
            "seller": {"full_name": payload.seller_name, "external_id": payload.seller_external_id, "store_name": payload.store_name},
            "summary": build_personal_training_kpi_summary_payload(seller={"full_name": payload.seller_name}, training_profile={}, program_cards=[], kpi=payload.kpi),
            "programs": [],
        }

    programs = (await db.execute(select(ConsultantTrainingProgram).where(ConsultantTrainingProgram.status == "active").order_by(ConsultantTrainingProgram.order_index.asc()))).scalars().all()
    all_steps: list[ConsultantTrainingStep] = []
    combined_progress: dict[str, dict] = {}
    program_cards: list[dict] = []
    for program in programs:
        steps = await _program_steps(db, program.id)
        all_steps.extend(steps)
        enrollment = await db.scalar(select(ConsultantTrainingEnrollment).where(ConsultantTrainingEnrollment.program_id == program.id, ConsultantTrainingEnrollment.seller_user_id == seller.id))
        step_progress = (enrollment.meta or {}).get("step_progress", {}) if enrollment else {}
        combined_progress.update(step_progress)
        structure = build_program_structure_payload(program=program_payload(program), modules=[], steps=[step_payload(step) for step in steps], step_progress=step_progress)
        card = build_program_card_payload(
            program=program_payload(program),
            enrollment={
                **(enrollment_payload(enrollment) or {}),
                "completed_steps": structure["progress"].get("completed_steps", 0),
                "total_steps": structure["progress"].get("total_steps", 0),
                "pending_reviews": 0,
                "revision_count": 0,
            },
            next_assignment=structure.get("next_step"),
        )
        program_cards.append(card)
    profile = build_competency_profile_payload(steps=[step_payload(step) for step in all_steps], step_progress=combined_progress)
    summary = build_personal_training_kpi_summary_payload(seller=user_payload(seller), training_profile=profile, program_cards=program_cards, kpi=payload.kpi)
    return {"found": True, "seller": user_payload(seller), "summary": summary, "programs": program_cards}


def _extract_shift_rows_for_user(*, user: User, kpi_row: dict | None = None) -> list[dict]:
    preferences = user.preferences or {}
    if not isinstance(preferences, dict):
        preferences = {}
    candidates = [
        (kpi_row or {}).get("shifts"),
        (kpi_row or {}).get("schedule"),
        preferences.get("shifts"),
        preferences.get("schedule"),
        preferences.get("seller_shifts"),
    ]
    for value in candidates:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


@router.get("/profile/training/mentor/session")
async def get_seller_training_mentor_session(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    kpi_row: dict = {}
    kpi_error: str | None = None
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=subject_user, month=month)
        kpi_row = next((row for row in kpi_dashboard.get("sellers", []) if _kpi_row_matches_user(row, subject_user)), {})
    except Exception as exc:
        kpi_error = str(exc)
    summary, program_cards = await _seller_training_summary_for_user(db, subject_user, kpi=kpi_row)
    daily_focus = build_seller_daily_training_focus_payload(seller=user_payload(subject_user), training_summary=summary, kpi=kpi_row)
    shift_rows = _extract_shift_rows_for_user(user=subject_user, kpi_row=kpi_row)
    daily_focus = build_schedule_aware_training_focus_payload(daily_focus=daily_focus, shifts=shift_rows)
    current_task = build_current_learning_task_payload(
        programs=program_cards,
        daily_focus=daily_focus,
        competency_profile={"weakest_competencies": summary.get("weakest_competencies") or []},
    )
    task = current_task.get("primary_task") or {}
    published_materials = (await db.execute(
        select(ConsultantTrainingMaterial)
        .where(ConsultantTrainingMaterial.status == "published")
        .order_by(ConsultantTrainingMaterial.order_index.asc(), ConsultantTrainingMaterial.created_at.asc())
    )).scalars().all()
    single_material = published_materials[0] if len(published_materials) == 1 else None
    program_id = UUID(task["program_id"]) if task.get("program_id") else None
    assigned_program = await _assigned_training_program_for_user(db, subject_user.id)
    fallback_material = single_material
    if assigned_program:
        program_id = assigned_program.id
        assigned_program_materials = [material for material in published_materials if material.program_code == assigned_program.code]
        fallback_material = assigned_program_materials[0] if assigned_program_materials else None
        current_task["primary_task"] = {
            **task,
            "program_id": str(assigned_program.id),
            "program_code": assigned_program.code,
            "program_title": assigned_program.title,
            "title": (fallback_material.title if fallback_material else assigned_program.title),
            "status": task.get("status") or "available",
        }
        task = current_task.get("primary_task") or {}
    if single_material and single_material.program_code and not assigned_program:
        material_program = await db.scalar(select(ConsultantTrainingProgram).where(
            ConsultantTrainingProgram.code == single_material.program_code,
            ConsultantTrainingProgram.status == "active",
        ))
        if material_program:
            program_id = material_program.id
            current_task["primary_task"] = {
                **task,
                "program_id": str(material_program.id),
                "program_code": material_program.code,
                "program_title": material_program.title,
                "title": single_material.title,
                "status": "available",
            }
    step_materials = await _seller_step_materials_payload(db, subject_user, program_id=program_id, fallback_material=fallback_material)
    session = build_training_mentor_session_payload(current_task=current_task, step_materials=step_materials, daily_focus=daily_focus, current_material=step_materials.get("current_material"))
    return {
        "seller": user_payload(subject_user),
        "found_kpi": bool(kpi_row),
        "kpi_error": kpi_error,
        "session": session,
        "current_task": current_task,
        "step_materials": step_materials,
    }


@router.get("/profile/training/current-task")
async def get_seller_current_learning_task(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    kpi_row: dict = {}
    kpi_error: str | None = None
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=subject_user, month=month)
        kpi_row = next((row for row in kpi_dashboard.get("sellers", []) if _kpi_row_matches_user(row, subject_user)), {})
    except Exception as exc:
        kpi_error = str(exc)
    summary, program_cards = await _seller_training_summary_for_user(db, subject_user, kpi=kpi_row)
    daily_focus = build_seller_daily_training_focus_payload(seller=user_payload(subject_user), training_summary=summary, kpi=kpi_row)
    shift_rows = _extract_shift_rows_for_user(user=subject_user, kpi_row=kpi_row)
    daily_focus = build_schedule_aware_training_focus_payload(daily_focus=daily_focus, shifts=shift_rows)
    current_task = build_current_learning_task_payload(
        programs=program_cards,
        daily_focus=daily_focus,
        competency_profile={"weakest_competencies": summary.get("weakest_competencies") or []},
    )
    career_level = build_seller_career_level_payload(
        competency_profile=summary,
        kpi_summary=kpi_row,
        programs=program_cards,
    )
    return {
        "seller": user_payload(subject_user),
        "found_kpi": bool(kpi_row),
        "kpi_error": kpi_error,
        "current_task": current_task,
        "career_level": career_level,
        "daily_focus": daily_focus,
        "summary": summary,
        "programs": program_cards,
    }


@router.get("/profile/training/daily-focus")
async def get_seller_training_daily_focus(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    kpi_row: dict = {}
    kpi_error: str | None = None
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=subject_user, month=month)
        kpi_row = next((row for row in kpi_dashboard.get("sellers", []) if _kpi_row_matches_user(row, subject_user)), {})
    except Exception as exc:
        kpi_error = str(exc)
    summary, program_cards = await _seller_training_summary_for_user(db, subject_user, kpi=kpi_row)
    daily_focus = build_seller_daily_training_focus_payload(seller=user_payload(subject_user), training_summary=summary, kpi=kpi_row)
    shift_rows = _extract_shift_rows_for_user(user=subject_user, kpi_row=kpi_row)
    daily_focus = build_schedule_aware_training_focus_payload(daily_focus=daily_focus, shifts=shift_rows)
    return {
        "found_kpi": bool(kpi_row),
        "kpi_error": kpi_error,
        "seller": user_payload(subject_user),
        "summary": summary,
        "daily_focus": daily_focus,
        "schedule_context": daily_focus.get("schedule_context"),
        "programs": program_cards,
    }


@router.post("/profile/training/shift-reflections")
async def create_seller_shift_reflection(
    payload: ShiftReflectionCreateRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    reflection_input = {
        "worked_well": payload.worked_well,
        "difficult_scenario": payload.difficult_scenario,
        "glame_argument": payload.glame_argument,
        "needs_help": payload.needs_help,
    }
    evaluation = build_shift_reflection_payload(reflection=reflection_input, daily_focus=payload.daily_focus, include_internal=True)
    reflection = ConsultantTrainingShiftReflection(
        seller_user_id=subject_user.id,
        shift_date=payload.shift_date,
        store_name=payload.store_name,
        daily_focus_snapshot=payload.daily_focus or {},
        reflection_payload=reflection_input,
        ai_score=evaluation.get("ai_score"),
        ai_evaluation=evaluation,
        status=evaluation.get("status", "submitted"),
        risk_flags=evaluation.get("risk_flags", []),
        manager_note=evaluation.get("manager_note"),
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return {"reflection": shift_reflection_payload(reflection, include_internal=False), "message": "Рефлексия сохранена. Если нужен разбор, руководитель увидит сигнал мягко и без публичной оценки."}


@router.get("/profile/training/shift-reflections")
async def list_seller_shift_reflections(
    limit: int = Query(default=20, ge=1, le=100),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    rows = (await db.execute(
        select(ConsultantTrainingShiftReflection)
        .where(ConsultantTrainingShiftReflection.seller_user_id == subject_user.id)
        .order_by(desc(ConsultantTrainingShiftReflection.created_at))
        .limit(limit)
    )).scalars().all()
    return {"reflections": [shift_reflection_payload(item, include_internal=False) for item in rows]}


@router.get("/admin/consultant-training/shift-reflections")
async def list_admin_shift_reflections(
    status: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingShiftReflection, User).join(User, User.id == ConsultantTrainingShiftReflection.seller_user_id).order_by(desc(ConsultantTrainingShiftReflection.created_at)).limit(limit)
    if status:
        query = query.where(ConsultantTrainingShiftReflection.status == normalize_shift_reflection_status(status))
    rows = (await db.execute(query)).all()
    return {"reflections": [shift_reflection_payload(reflection, seller, include_internal=True) for reflection, seller in rows]}


@router.patch("/admin/consultant-training/shift-reflections/{reflection_id}/review")
async def review_admin_shift_reflection(
    reflection_id: UUID,
    payload: ShiftReflectionReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    reflection = await db.get(ConsultantTrainingShiftReflection, reflection_id)
    if not reflection:
        raise HTTPException(status_code=404, detail="Рефлексия смены не найдена")
    reflection.status = normalize_shift_reflection_status(payload.status)
    reflection.manager_feedback = payload.manager_feedback
    reflection.reviewed_by_user_id = current_user.id
    reflection.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(reflection)
    return shift_reflection_payload(reflection, include_internal=True)


@router.post("/admin/consultant-training/coaching-actions")
async def create_admin_coaching_action(
    payload: CoachingActionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    reflection = await db.get(ConsultantTrainingShiftReflection, payload.reflection_id) if payload.reflection_id else None
    seller_user_id = payload.seller_user_id or (reflection.seller_user_id if reflection else None)
    if not seller_user_id:
        raise HTTPException(status_code=400, detail="Нужен reflection_id или seller_user_id")
    source = reflection or {"seller_user_id": seller_user_id}
    draft = build_coaching_action_payload(reflection=source, manager_user_id=str(current_user.id), planned_for=payload.planned_for.isoformat() if payload.planned_for else None)
    action = ConsultantTrainingCoachingAction(
        reflection_id=reflection.id if reflection else None,
        seller_user_id=seller_user_id,
        created_by_user_id=current_user.id,
        status=draft["status"],
        planned_for=payload.planned_for,
        store_name=draft.get("store_name"),
        coaching_topic=payload.coaching_topic or draft["coaching_topic"],
        competency=draft.get("competency"),
        kpi_metric=draft.get("kpi_metric"),
        risk_flags=draft.get("risk_flags") or [],
        manager_script=payload.manager_script or draft.get("manager_script"),
        seller_next_step=payload.seller_next_step or draft.get("seller_next_step"),
    )
    db.add(action)
    if reflection and reflection.status == "needs_coaching":
        reflection.status = "reviewed"
        reflection.reviewed_by_user_id = current_user.id
        reflection.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(action)
    seller = await db.get(User, seller_user_id)
    return {"coaching_action": coaching_action_payload(action, seller, include_internal=True), "message": "Coaching-задача создана"}


@router.get("/admin/consultant-training/coaching-actions")
async def list_admin_coaching_actions(
    status: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingCoachingAction, User).join(User, User.id == ConsultantTrainingCoachingAction.seller_user_id).order_by(desc(ConsultantTrainingCoachingAction.created_at)).limit(limit)
    if status:
        query = query.where(ConsultantTrainingCoachingAction.status == normalize_coaching_action_status(status))
    rows = (await db.execute(query)).all()
    return {"coaching_actions": [coaching_action_payload(action, seller, include_internal=True) for action, seller in rows]}


@router.patch("/admin/consultant-training/coaching-actions/{action_id}")
async def update_admin_coaching_action(
    action_id: UUID,
    payload: CoachingActionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    action = await db.get(ConsultantTrainingCoachingAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Coaching-задача не найдена")
    now = datetime.now(timezone.utc)
    if payload.status is not None:
        action.status = normalize_coaching_action_status(payload.status)
        if action.status == "discussed":
            action.discussed_at = action.discussed_at or now
        if action.status == "resolved":
            action.discussed_at = action.discussed_at or now
            action.resolved_at = action.resolved_at or now
    if payload.planned_for is not None:
        action.planned_for = payload.planned_for
    if payload.manager_result is not None:
        action.manager_result = payload.manager_result
    if payload.seller_visible_feedback is not None:
        action.seller_visible_feedback = payload.seller_visible_feedback
    await db.commit()
    await db.refresh(action)
    seller = await db.get(User, action.seller_user_id)
    return coaching_action_payload(action, seller, include_internal=True)


@router.get("/profile/training/coaching-actions")
async def list_seller_coaching_actions(
    limit: int = Query(default=20, ge=1, le=100),
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    rows = (await db.execute(
        select(ConsultantTrainingCoachingAction)
        .where(ConsultantTrainingCoachingAction.seller_user_id == subject_user.id, ConsultantTrainingCoachingAction.status.in_(["planned", "discussed", "resolved"]))
        .order_by(desc(ConsultantTrainingCoachingAction.created_at))
        .limit(limit)
    )).scalars().all()
    return {"coaching_actions": [coaching_action_payload(action, include_internal=False) for action in rows]}


@router.get("/admin/consultant-training/account-matching")
async def get_admin_training_account_matching(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    users = (await db.execute(select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"])).order_by(User.full_name.asc()))).scalars().all()
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=current_user, month=month)
        payload = build_seller_training_account_matching_payload(kpi_sellers=kpi_dashboard.get("sellers", []), users=users)
        payload["month"] = kpi_dashboard.get("month")
        payload["data_quality"] = kpi_dashboard.get("data_quality", {})
        return payload
    except Exception as exc:
        payload = build_seller_training_account_matching_payload(kpi_sellers=[], users=users)
        payload["error"] = "KPI-продавцы временно недоступны для диагностики сопоставления"
        payload["detail"] = str(exc)
        return payload


@router.post("/admin/consultant-training/account-matching/link")
async def link_admin_training_account(
    payload: TrainingAccountLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    user = await db.get(User, payload.user_id)
    if not user or user.is_customer or user.role not in {"seller", "manager", "admin"}:
        raise HTTPException(status_code=404, detail="Аккаунт сотрудника не найден")
    user.preferences = build_seller_training_account_preferences_update(
        current_preferences=user.preferences or {},
        seller_external_id=payload.seller_external_id,
        seller_name=payload.seller_name,
        store_name=payload.store_name,
        manager_user_id=str(current_user.id),
    )
    await db.commit()
    await db.refresh(user)
    return {"user": user_payload(user), "preferences": user.preferences or {}, "message": "Аккаунт продавца связан с 1C/KPI строкой"}


@router.get("/admin/consultant-training/analytics")
async def get_admin_training_analytics(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    competency_response = await list_admin_training_competencies(db=db, current_user=current_user)
    step_rows = (await db.execute(
        select(ConsultantTrainingStepSubmission, ConsultantTrainingStep)
        .join(ConsultantTrainingStep, ConsultantTrainingStep.id == ConsultantTrainingStepSubmission.step_id)
        .order_by(desc(ConsultantTrainingStepSubmission.created_at))
        .limit(300)
    )).all()
    step_payloads = [step_submission_payload(submission, step, include_internal=True) for submission, step in step_rows]
    mentor_messages = (await db.execute(
        select(ConsultantTrainingMentorMessage)
        .order_by(desc(ConsultantTrainingMentorMessage.created_at))
        .limit(300)
    )).scalars().all()
    mentor_payloads = [mentor_message_payload(message, include_internal=True) for message in mentor_messages]
    attestations = (await db.execute(select(ConsultantTrainingAttestation).order_by(desc(ConsultantTrainingAttestation.created_at)).limit(300))).scalars().all()
    attestation_payloads = [attestation_payload(item, item.competency_snapshot or {}, include_internal=True) for item in attestations]
    analytics = build_management_analytics_payload(
        seller_profiles=competency_response.get("sellers", []),
        step_submissions=step_payloads,
        mentor_messages=mentor_payloads,
        attestations=attestation_payloads,
    )
    try:
        kpi_dashboard = await SellerKPIService(db).dashboard(current_user=current_user, month=month)
        analytics["kpi_linkage"] = build_training_kpi_linkage_payload(
            seller_profiles=competency_response.get("sellers", []),
            kpi_sellers=kpi_dashboard.get("sellers", []),
        )
        analytics["kpi_linkage"]["month"] = kpi_dashboard.get("month")
        analytics["kpi_linkage"]["data_quality"] = kpi_dashboard.get("data_quality", {})
    except Exception as exc:  # keep training analytics available if KPI source is temporarily stale
        analytics["kpi_linkage"] = {
            "summary": {"matched_sellers": 0, "low_kpi_and_low_training": 0, "avg_completion_low_training": None, "avg_completion_trained": None},
            "seller_actions": [],
            "recommendations": [],
            "error": "KPI-связка временно недоступна",
            "detail": str(exc),
        }
    return analytics


@router.get("/profile/training/attestations")
async def list_seller_attestations(
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    rows = (await db.execute(select(ConsultantTrainingAttestation).where(ConsultantTrainingAttestation.seller_user_id == subject_user.id).order_by(desc(ConsultantTrainingAttestation.created_at)))).scalars().all()
    return {"attestations": [attestation_payload(row, include_internal=False) for row in rows]}


@router.post("/profile/training/attestations")
async def start_seller_attestation(
    payload: AttestationStartRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    program = await db.get(ConsultantTrainingProgram, payload.program_id)
    if not program or program.status != "active":
        raise HTTPException(status_code=404, detail="Программа обучения не найдена")
    enrollment, profile = await _seller_competency_profile_for_program(db, program, subject_user.id)
    if not profile.get("attestation_ready"):
        raise HTTPException(status_code=409, detail="Пока недостаточно закрытых компетенций для аттестации")
    task_payload = {
        "title": "Аттестация GLAME",
        "cases": [
            "Опишите клиентский сценарий и подберите украшение через эффект на образ.",
            "Сформулируйте спокойную GLAME-фразу без давления.",
            "Назовите, какие компетенции применены в ответе.",
        ],
    }
    attestation = ConsultantTrainingAttestation(
        program_id=program.id,
        enrollment_id=enrollment.id if enrollment else None,
        seller_user_id=subject_user.id,
        attestation_type=payload.attestation_type,
        status="draft",
        task_payload=task_payload,
        competency_snapshot=profile,
    )
    db.add(attestation)
    await db.commit()
    await db.refresh(attestation)
    return attestation_payload(attestation, profile, include_internal=False)


@router.post("/profile/training/attestations/{attestation_id}/submit")
async def submit_seller_attestation(
    attestation_id: UUID,
    payload: AttestationSubmitRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    attestation = await db.get(ConsultantTrainingAttestation, attestation_id)
    if not attestation or attestation.seller_user_id != subject_user.id:
        raise HTTPException(status_code=404, detail="Аттестация не найдена")
    text_answer = " ".join(str(value) for value in (payload.answer_payload or {}).values())
    evaluation = evaluate_submission_quality(text_answer, expected_focus="аттестация GLAME эффект образ клиент фраза")
    attestation.answer_payload = payload.answer_payload or {}
    attestation.ai_score = evaluation.get("score")
    attestation.ai_evaluation = evaluation
    attestation.status = "review_pending"
    attestation.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attestation)
    return attestation_payload(attestation, attestation.competency_snapshot or {}, include_internal=False)


@router.get("/admin/consultant-training/attestations")
async def list_admin_attestations(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingAttestation, User).join(User, User.id == ConsultantTrainingAttestation.seller_user_id).order_by(desc(ConsultantTrainingAttestation.created_at))
    if status:
        query = query.where(ConsultantTrainingAttestation.status == status)
    rows = (await db.execute(query)).all()
    return {"attestations": [{**attestation_payload(attestation, attestation.competency_snapshot or {}, include_internal=True), "seller": user_payload(seller)} for attestation, seller in rows]}


@router.patch("/admin/consultant-training/attestations/{attestation_id}/review")
async def review_admin_attestation(
    attestation_id: UUID,
    payload: AttestationReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    attestation = await db.get(ConsultantTrainingAttestation, attestation_id)
    if not attestation:
        raise HTTPException(status_code=404, detail="Аттестация не найдена")
    decision = payload.manager_decision if payload.manager_decision in {"passed", "failed", "revision_requested", "certified"} else "passed"
    attestation.manager_decision = decision
    attestation.manager_feedback = payload.manager_feedback
    attestation.certified_level = payload.certified_level or (attestation.competency_snapshot or {}).get("level")
    attestation.reviewed_by_user_id = current_user.id
    attestation.reviewed_at = datetime.now(timezone.utc)
    attestation.status = "certified" if decision in {"passed", "certified"} else decision
    enrollment = await db.get(ConsultantTrainingEnrollment, attestation.enrollment_id) if attestation.enrollment_id else None
    if enrollment and attestation.status == "certified":
        enrollment.status = "certified"
        enrollment.completed_at = enrollment.completed_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attestation)
    return attestation_payload(attestation, attestation.competency_snapshot or {}, include_internal=True)


@router.get("/admin/consultant-training/topics")
async def list_admin_topics(
    month: str | None = Query(default=None, description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingTopic).order_by(ConsultantTrainingTopic.lesson_date.asc())
    if month:
        try:
            year, month_num = [int(part) for part in month.split("-", 1)]
            query = query.where(
                and_(
                    func.extract("year", ConsultantTrainingTopic.lesson_date) == year,
                    func.extract("month", ConsultantTrainingTopic.lesson_date) == month_num,
                )
            )
        except Exception:
            raise HTTPException(status_code=400, detail="month должен быть в формате YYYY-MM")
    topics = (await db.execute(query)).scalars().all()
    payload = []
    for topic in topics:
        assigned = await db.scalar(select(func.count()).select_from(ConsultantTrainingAssignment).where(ConsultantTrainingAssignment.topic_id == topic.id)) or 0
        submitted = await db.scalar(select(func.count()).select_from(ConsultantTrainingSubmission).where(ConsultantTrainingSubmission.topic_id == topic.id)) or 0
        accepted = await db.scalar(select(func.count()).select_from(ConsultantTrainingSubmission).where(ConsultantTrainingSubmission.topic_id == topic.id, ConsultantTrainingSubmission.review_status.in_(["approved", "sent_to_consultant"]))) or 0
        payload.append(topic_payload(topic, assignments=assigned, submitted=submitted, accepted=accepted))
    return {"topics": payload}


@router.post("/admin/consultant-training/topics")
async def create_admin_topic(
    payload: TopicCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    topic = ConsultantTrainingTopic(
        lesson_date=payload.lesson_date,
        title=payload.title,
        theme=payload.theme,
        goal=payload.goal,
        material_text=payload.material_text,
        assignment_text=payload.assignment_text,
        focus_text=payload.focus_text,
        status=normalize_topic_status(payload.status),
        meta=payload.meta or {},
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic_payload(topic)


@router.patch("/admin/consultant-training/topics/{topic_id}")
async def update_admin_topic(
    topic_id: UUID,
    payload: TopicUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    topic = await _get_topic_or_404(db, topic_id)
    for field in ["lesson_date", "title", "theme", "goal", "material_text", "assignment_text", "focus_text", "approval_comment", "meta"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(topic, field, value)
    if payload.status is not None:
        topic.status = normalize_topic_status(payload.status)
    await db.commit()
    await db.refresh(topic)
    return topic_payload(topic)


@router.post("/admin/consultant-training/topics/{topic_id}/approve")
async def approve_topic(
    topic_id: UUID,
    payload: TopicApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    topic = await _get_topic_or_404(db, topic_id)
    topic.approval_comment = payload.comment
    if payload.approved:
        topic.status = "approved"
        topic.approved_by_user_id = current_user.id
        topic.approved_at = datetime.now(timezone.utc)
    else:
        topic.status = "needs_revision"
    await db.commit()
    await db.refresh(topic)
    return topic_payload(topic)


@router.post("/admin/consultant-training/topics/{topic_id}/publish")
async def publish_topic(
    topic_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    topic = await _get_topic_or_404(db, topic_id)
    if topic.status not in {"approved", "ready_to_publish", "sent_to_consultants"}:
        raise HTTPException(status_code=409, detail="Материал нельзя отправить без согласования")
    sellers = (await db.execute(select(User).where(User.is_customer.is_(False), User.role.in_(["seller", "manager", "admin"])).order_by(User.full_name.asc()))).scalars().all()
    created = 0
    for seller in sellers:
        existing = await db.scalar(select(ConsultantTrainingAssignment).where(ConsultantTrainingAssignment.topic_id == topic.id, ConsultantTrainingAssignment.seller_user_id == seller.id))
        if not existing:
            db.add(ConsultantTrainingAssignment(topic_id=topic.id, seller_user_id=seller.id, status="not_opened"))
            created += 1
    topic.status = "sent_to_consultants"
    topic.published_at = topic.published_at or datetime.now(timezone.utc)
    await db.commit()
    return {"topic": topic_payload(topic), "created_assignments": created, "seller_count": len(sellers)}


@router.get("/admin/consultant-training/submissions")
async def list_submissions_for_review(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    query = select(ConsultantTrainingSubmission, User).join(User, User.id == ConsultantTrainingSubmission.seller_user_id).order_by(desc(ConsultantTrainingSubmission.created_at))
    if status:
        query = query.where(ConsultantTrainingSubmission.review_status == status)
    rows = (await db.execute(query)).all()
    return {"submissions": [submission_payload(sub, seller) for sub, seller in rows]}


@router.post("/admin/consultant-training/submissions/{submission_id}/review")
async def review_submission(
    submission_id: UUID,
    payload: SubmissionReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(MANAGER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    submission = await db.get(ConsultantTrainingSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Ответ не найден")
    now = datetime.now(timezone.utc)
    submission.review_status = payload.review_status
    submission.manager_feedback = payload.manager_feedback
    submission.consultant_feedback = payload.consultant_feedback
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = now
    if payload.send_to_consultant:
        submission.review_status = "sent_to_consultant"
        submission.sent_to_consultant_at = now
    assignment = await db.get(ConsultantTrainingAssignment, submission.assignment_id) if submission.assignment_id else None
    if assignment:
        if payload.review_status in {"revision_requested", "needs_revision"}:
            assignment.status = "needs_revision"
        elif submission.review_status in {"approved", "sent_to_consultant"}:
            assignment.status = "accepted"
            assignment.completed_at = now
    await db.commit()
    await db.refresh(submission)
    return submission_payload(submission)


@router.get("/profile/training/topics")
async def list_seller_training(
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    rows = (await db.execute(
        select(ConsultantTrainingAssignment, ConsultantTrainingTopic)
        .join(ConsultantTrainingTopic, ConsultantTrainingTopic.id == ConsultantTrainingAssignment.topic_id)
        .where(ConsultantTrainingAssignment.seller_user_id == subject_user.id)
        .order_by(ConsultantTrainingTopic.lesson_date.desc())
    )).all()
    return {"items": [{"assignment": assignment_payload(a), "topic": topic_payload(t)} for a, t in rows]}


@router.get("/profile/training/today")
async def get_today_training(
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    today = date.today()
    row = (await db.execute(
        select(ConsultantTrainingAssignment, ConsultantTrainingTopic)
        .join(ConsultantTrainingTopic, ConsultantTrainingTopic.id == ConsultantTrainingAssignment.topic_id)
        .where(ConsultantTrainingAssignment.seller_user_id == subject_user.id, ConsultantTrainingTopic.lesson_date == today)
    )).first()
    if not row:
        return {"assignment": None, "topic": None}
    assignment, topic = row
    return {"assignment": assignment_payload(assignment), "topic": topic_payload(topic)}


@router.post("/profile/training/topics/{topic_id}/open")
async def open_seller_topic(
    topic_id: UUID,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    assignment = await db.scalar(select(ConsultantTrainingAssignment).where(ConsultantTrainingAssignment.topic_id == topic_id, ConsultantTrainingAssignment.seller_user_id == subject_user.id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Материал не назначен этому продавцу")
    if assignment.status == "not_opened":
        assignment.status = "opened"
        assignment.opened_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(assignment)
    return assignment_payload(assignment)


@router.post("/profile/training/topics/{topic_id}/submit")
async def submit_training_answer(
    topic_id: UUID,
    payload: SubmissionCreateRequest,
    seller_user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role(SELLER_ROLES)),
):
    await ensure_consultant_training_schema(db)
    subject_user = await _training_subject_user(db, current_user, seller_user_id)
    topic = await _get_topic_or_404(db, topic_id)
    assignment = await db.scalar(select(ConsultantTrainingAssignment).where(ConsultantTrainingAssignment.topic_id == topic_id, ConsultantTrainingAssignment.seller_user_id == subject_user.id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Материал не назначен этому продавцу")
    voice_metadata = build_voice_answer_metadata(payload.voice_answer, current_user=current_user)
    answer_text = build_answer_text_with_voice(payload.practice_answer, voice_metadata)
    evaluation = evaluate_submission_quality(answer_text, expected_focus=topic.assignment_text or topic.theme or topic.title)
    evaluation = attach_voice_metadata_to_evaluation(evaluation, voice_metadata)
    review_status = "revision_draft" if should_request_revision(evaluation) else "review_pending"
    submission = ConsultantTrainingSubmission(
        topic_id=topic.id,
        assignment_id=assignment.id,
        seller_user_id=subject_user.id,
        practice_answer=answer_text,
        evening_review=payload.evening_review,
        ai_score=evaluation["score"],
        ai_evaluation=evaluation,
        review_status=review_status,
    )
    assignment.status = "submitted"
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return {"submission": submission_payload(submission), "message": "Ответ отправлен на проверку"}
