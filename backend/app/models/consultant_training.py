from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class ConsultantTrainingProgram(Base):
    __tablename__ = "consultant_training_programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(80), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    program_type = Column(String(80), nullable=False, default="custom", index=True)
    status = Column(String(50), nullable=False, default="active", index=True)
    audience_rules = Column(JSON, nullable=False, default=dict)
    is_required = Column(Boolean, nullable=False, default=True)
    order_index = Column(Integer, nullable=False, default=100)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConsultantTrainingModule(Base):
    __tablename__ = "consultant_training_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=100)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConsultantTrainingStep(Base):
    __tablename__ = "consultant_training_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    lesson_text = Column(Text, nullable=True)
    practice_text = Column(Text, nullable=True)
    answer_template = Column(Text, nullable=True)
    assessment_rubric = Column(JSON, nullable=False, default=dict)
    competencies = Column(JSON, nullable=False, default=list)
    unlock_rule = Column(JSON, nullable=False, default=dict)
    is_required = Column(Boolean, nullable=False, default=True)
    order_index = Column(Integer, nullable=False, default=100)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConsultantTrainingAttestation(Base):
    __tablename__ = "consultant_training_attestations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_enrollments.id", ondelete="CASCADE"), nullable=True, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attestation_type = Column(String(80), nullable=False, default="trainee_final", index=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    task_payload = Column(JSON, nullable=False, default=dict)
    answer_payload = Column(JSON, nullable=False, default=dict)
    competency_snapshot = Column(JSON, nullable=False, default=dict)
    ai_score = Column(Integer, nullable=True)
    ai_evaluation = Column(JSON, nullable=False, default=dict)
    manager_decision = Column(String(50), nullable=True)
    manager_feedback = Column(Text, nullable=True)
    certified_level = Column(String(80), nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_attestations_review", "status", "created_at"),
    )


class ConsultantTrainingShiftReflection(Base):
    __tablename__ = "consultant_training_shift_reflections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_date = Column(Date, nullable=True, index=True)
    store_name = Column(String(255), nullable=True, index=True)
    daily_focus_snapshot = Column(JSON, nullable=False, default=dict)
    reflection_payload = Column(JSON, nullable=False, default=dict)
    ai_score = Column(Integer, nullable=True)
    ai_evaluation = Column(JSON, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="submitted", index=True)
    risk_flags = Column(JSON, nullable=False, default=list)
    manager_note = Column(Text, nullable=True)
    manager_feedback = Column(Text, nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_shift_reflections_seller_date", "seller_user_id", "shift_date"),
        Index("ix_consultant_training_shift_reflections_status_created", "status", "created_at"),
    )


class ConsultantTrainingCoachingAction(Base):
    __tablename__ = "consultant_training_coaching_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reflection_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_shift_reflections.id", ondelete="SET NULL"), nullable=True, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="new", index=True)
    planned_for = Column(Date, nullable=True, index=True)
    store_name = Column(String(255), nullable=True, index=True)
    coaching_topic = Column(Text, nullable=False)
    competency = Column(String(255), nullable=True, index=True)
    kpi_metric = Column(String(255), nullable=True)
    risk_flags = Column(JSON, nullable=False, default=list)
    manager_script = Column(Text, nullable=True)
    seller_next_step = Column(Text, nullable=True)
    manager_result = Column(Text, nullable=True)
    seller_visible_feedback = Column(Text, nullable=True)
    discussed_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_coaching_actions_seller_status", "seller_user_id", "status"),
        Index("ix_consultant_training_coaching_actions_status_planned", "status", "planned_for"),
    )


class ConsultantTrainingMaterial(Base):
    __tablename__ = "consultant_training_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    topic = Column(String(255), nullable=False, default="Общее", index=True)
    category = Column(String(255), nullable=False, default="Библиотека GLAME", index=True)
    description = Column(Text, nullable=True)
    markdown_content = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="draft", index=True)
    tags = Column(JSON, nullable=False, default=list)
    source_type = Column(String(80), nullable=False, default="manual_md", index=True)
    extraction_metadata = Column(JSON, nullable=False, default=dict)
    program_code = Column(String(80), nullable=True, index=True)
    competencies = Column(JSON, nullable=False, default=list)
    internal_notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    order_index = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_materials_topic_status", "topic", "status"),
        Index("ix_consultant_training_materials_category_order", "category", "order_index"),
    )


class ConsultantTrainingMaterialSlide(Base):
    __tablename__ = "consultant_training_material_slides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    material_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    image_prompt = Column(Text, nullable=True)
    speaker_note = Column(Text, nullable=True)
    quiz_question = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    order_index = Column(Integer, nullable=False, default=100)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_material_slides_material_order", "material_id", "order_index"),
    )


class ConsultantTrainingMaterialSlideProgress(Base):
    __tablename__ = "consultant_training_material_slide_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    material_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_material_slides.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("slide_id", "seller_user_id", name="uq_consultant_training_slide_progress_seller"),
        Index("ix_consultant_training_slide_progress_material_seller", "material_id", "seller_user_id"),
    )


class ConsultantTrainingStepMaterial(Base):
    __tablename__ = "consultant_training_step_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_modules.id", ondelete="CASCADE"), nullable=True, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(80), nullable=False, default="primary_lesson", index=True)
    required_to_complete = Column(Boolean, nullable=False, default=True)
    order_index = Column(Integer, nullable=False, default=100)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("step_id", "material_id", "role", name="uq_consultant_training_step_material_role"),
        Index("ix_consultant_training_step_materials_step_order", "step_id", "order_index"),
    )


class ConsultantTrainingMaterialStatusHistory(Base):
    __tablename__ = "consultant_training_material_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    material_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False, index=True)
    note = Column(Text, nullable=True)
    changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_consultant_training_material_status_history_material_created", "material_id", "created_at"),
    )


class ConsultantTrainingMentorMessage(Base):
    __tablename__ = "consultant_training_mentor_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=True, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_role = Column(String(20), nullable=False, default="mentor", index=True)
    question_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=False)
    context = Column(JSON, nullable=False, default=dict)
    risk_flags = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_consultant_training_mentor_messages_seller_created", "seller_user_id", "created_at"),
    )


class ConsultantTrainingStepSubmission(Base):
    __tablename__ = "consultant_training_step_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_enrollments.id", ondelete="CASCADE"), nullable=True, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    practice_answer = Column(Text, nullable=False)
    evening_review = Column(Text, nullable=True)
    ai_score = Column(Integer, nullable=True)
    ai_evaluation = Column(JSON, nullable=False, default=dict)
    review_status = Column(String(50), nullable=False, default="review_pending", index=True)
    manager_feedback = Column(Text, nullable=True)
    consultant_feedback = Column(Text, nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    sent_to_consultant_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_step_submissions_review", "review_status", "created_at"),
    )


class ConsultantTrainingEnrollment(Base):
    __tablename__ = "consultant_training_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="available", index=True)
    current_topic_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_topics.id", ondelete="SET NULL"), nullable=True)
    average_score = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("program_id", "seller_user_id", name="uq_consultant_training_enrollment_program_seller"),
    )


class ConsultantTrainingTopic(Base):
    __tablename__ = "consultant_training_topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    theme = Column(String(500), nullable=True)
    goal = Column(Text, nullable=True)
    material_text = Column(Text, nullable=True)
    assignment_text = Column(Text, nullable=True)
    focus_text = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    approval_comment = Column(Text, nullable=True)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("lesson_date", name="uq_consultant_training_topics_lesson_date"),
        Index("ix_consultant_training_topics_status_date", "status", "lesson_date"),
    )


class ConsultantTrainingAssignment(Base):
    __tablename__ = "consultant_training_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_topics.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="not_opened", index=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("topic_id", "seller_user_id", name="uq_consultant_training_assignment_topic_seller"),
    )


class ConsultantTrainingSubmission(Base):
    __tablename__ = "consultant_training_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_topics.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("consultant_training_assignments.id", ondelete="CASCADE"), nullable=True, index=True)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    practice_answer = Column(Text, nullable=False)
    evening_review = Column(Text, nullable=True)
    ai_score = Column(Integer, nullable=True)
    ai_evaluation = Column(JSON, nullable=False, default=dict)
    review_status = Column(String(50), nullable=False, default="review_pending", index=True)
    manager_feedback = Column(Text, nullable=True)
    consultant_feedback = Column(Text, nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    sent_to_consultant_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_consultant_training_submissions_review", "review_status", "created_at"),
    )
