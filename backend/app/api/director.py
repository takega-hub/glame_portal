"""
API роутер для Director Agent.

Эндпоинты:
- POST /director/chat — отправить сообщение директору
- POST /director/tasks — создать задачу
- GET /director/tasks — получить список задач
- GET /director/memory — получить контекст памяти
- POST /director/knowledge — добавить знание в базу
- GET /director/knowledge/search — поиск по базе знаний
- GET /director/chat/search — поиск по истории чата
- GET /director/chat/history — история чата
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime
from pathlib import Path
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func as sql_func, update

from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.director_memory import (
    DirectorChatMessage,
    DirectorTask,
    DirectorMemory,
    DirectorKnowledge,
    DirectorConversationContext,
)
from app.models.knowledge_document import KnowledgeDocument
from app.models.agent_interaction import AgentInteractionTask, AgentInteractionLog, InteractionStatus
from app.agents.director_agent import DirectorAgent
from app.services.vector_service import vector_service
from app.services.pdf_processor import pdf_processor
from app.api.knowledge import _delete_document_by_id

router = APIRouter(prefix="/api/director", tags=["director"])

DIRECTOR_UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "director"
DIRECTOR_UPLOAD_MAX_BYTES = 30 * 1024 * 1024
DIRECTOR_ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".txt",
    ".md",
    ".csv",
    ".json",
}


def _safe_upload_filename(filename: str | None) -> str:
    raw = (filename or "file").strip().replace("\\", "/").split("/")[-1]
    safe = re.sub(r"[^A-Za-zА-Яа-я0-9._ -]+", "_", raw).strip(" .")
    return safe[:160] or "file"


def _extract_director_upload_text(filename: str, content: bytes, content_type: str | None) -> tuple[str, str]:
    lower = filename.lower()
    if lower.endswith(".pdf") or content_type == "application/pdf":
        text = pdf_processor.extract_text_from_pdf(content)
        return text, "pdf"

    if lower.endswith((".txt", ".md", ".csv", ".json")) or (content_type or "").startswith("text/"):
        for encoding in ("utf-8", "utf-8-sig", "cp1251"):
            try:
                return content.decode(encoding), "text"
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore"), "text"

    if (content_type or "").startswith("image/") or lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "", "image"

    return "", "file"


def _agent_task_to_director_card(task: AgentInteractionTask) -> dict:
    input_data = task.input_data or {}
    context = task.task_context or {}
    title = input_data.get("title") or context.get("title") or task.task_type.replace("_", " ")
    description = input_data.get("description") or input_data.get("expected_result") or task.error_message
    return {
        "id": str(task.id),
        "source": "agent_interaction",
        "title": title,
        "description": description,
        "task_type": task.task_type,
        "target_agent": task.target_agent,
        "priority": f"P{max(0, int(task.priority or 3) - 1)}",
        "status": task.status,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "assigned_to": task.target_agent,
        "execution_notes": context.get("board") or input_data.get("source_board"),
        "result_summary": input_data.get("result") or ((task.output_data or {}).get("summary") if task.output_data else None),
        "detailed_result": task.output_data,
        "extra_data": {
            "board": context.get("board") or input_data.get("source_board"),
            "source_agent": task.source_agent,
            "input_data": input_data,
            "task_context": context,
            "href": f"/ai-marketer/tasks/{task.id}",
        },
    }


def _director_task_to_card(task: DirectorTask) -> dict:
    data = task.to_dict()
    data["source"] = "director_task"
    data["extra_data"] = {**(data.get("extra_data") or {}), "href": None}
    return data


def _kanban_column_for_status(status: str) -> str:
    if status in {
        InteractionStatus.PENDING.value,
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING_APPROVAL.value,
        InteractionStatus.APPROVED.value,
        "pending",
    }:
        return "todo"
    if status in {
        InteractionStatus.VALIDATING.value,
        InteractionStatus.QUEUED.value,
        InteractionStatus.PROCESSING.value,
        "in_progress",
    }:
        return "in_progress"
    if status in {InteractionStatus.COMPLETED.value, "completed"}:
        return "done"
    if status in {
        InteractionStatus.FAILED.value,
        InteractionStatus.REJECTED.value,
        InteractionStatus.CANCELLED.value,
        "rejected",
    }:
        return "blocked"
    return "todo"


def _status_for_kanban_column(source: str, column_id: str) -> str:
    if source == "director_task":
        mapping = {
            "todo": "pending",
            "in_progress": "in_progress",
            "done": "completed",
            "blocked": "rejected",
        }
    else:
        mapping = {
            "todo": InteractionStatus.PENDING.value,
            "in_progress": InteractionStatus.PROCESSING.value,
            "done": InteractionStatus.COMPLETED.value,
            "blocked": InteractionStatus.CANCELLED.value,
        }
    if column_id not in mapping:
        raise HTTPException(status_code=400, detail="Unknown kanban column")
    return mapping[column_id]


ACTIVE_CHAT_STATUSES = ("pending", "processing", "completed")


@router.post("/chat")
async def chat_with_director(
    message: str = Body(..., embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    category: Optional[str] = Body(None, embed=True),
    model: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отправить сообщение AI-директору. Директор ответит, используя контекст памяти и базы знаний."""
    agent = DirectorAgent(db)
    result = await agent.process_chat_message(
        user_id=current_user.id,
        message=message,
        session_id=session_id,
        category=category,
        model=model,
    )
    return result


@router.post("/chat/upload")
async def upload_file_to_director_chat(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
    add_to_knowledge: bool = Form(False),
    knowledge_category: str = Form("document"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Загрузить файл в чат директора и при необходимости сохранить его в базу знаний директора."""
    filename = _safe_upload_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in DIRECTOR_ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются PDF, изображения, TXT, MD, CSV и JSON файлы.",
        )

    content = await file.read()
    if len(content) > DIRECTOR_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Файл слишком большой. Максимум 30 МБ.")
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")

    user_folder = DIRECTOR_UPLOAD_ROOT / str(current_user.id)
    user_folder.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}_{filename}"
    stored_path = user_folder / stored_filename
    stored_path.write_bytes(content)
    public_url = f"/uploads/director/{current_user.id}/{stored_filename}"

    extraction_error: Optional[str] = None
    extracted_text = ""
    detected_type = "file"
    try:
        extracted_text, detected_type = _extract_director_upload_text(filename, content, file.content_type)
    except Exception as exc:
        extraction_error = str(exc)
        detected_type = "pdf" if suffix == ".pdf" else "file"

    text_preview = extracted_text.strip()[:1200] if extracted_text else ""
    user_note = (message or "").strip()
    display_message = f"Загружен файл: {filename}"
    if user_note:
        display_message = f"{display_message}\nКомментарий: {user_note}"

    file_meta = {
        "filename": filename,
        "stored_filename": stored_filename,
        "url": public_url,
        "content_type": file.content_type,
        "file_size": len(content),
        "detected_type": detected_type,
        "add_to_knowledge": add_to_knowledge,
        "knowledge_category": knowledge_category,
        "extracted_text_preview": text_preview,
        "extraction_error": extraction_error,
    }

    user_message = DirectorChatMessage(
        user_id=current_user.id,
        message=display_message,
        message_type="file",
        message_direction="user",
        category="knowledge" if add_to_knowledge else "file",
        priority="P2",
        session_id=session_id,
        extra_data={"file": file_meta},
        status="completed",
        is_important=add_to_knowledge,
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    knowledge_result = None
    if add_to_knowledge:
        knowledge_content_parts = [
            f"Файл: {filename}",
            f"Тип: {detected_type}",
            f"Комментарий пользователя: {user_note}" if user_note else None,
            extracted_text.strip() if extracted_text else None,
        ]
        knowledge_content = "\n\n".join([part for part in knowledge_content_parts if part])
        if not extracted_text and detected_type == "image":
            knowledge_content += "\n\nИзображение сохранено как вложение. Для анализа содержимого требуется визуальное описание или отдельный OCR/vision-анализ."
        elif not extracted_text:
            knowledge_content += "\n\nТекст из файла не извлечен; сохранены метаданные и ссылка на вложение."

        agent = DirectorAgent(db)
        knowledge_result = await agent.add_to_knowledge(
            user_id=current_user.id,
            title=filename,
            content=knowledge_content,
            category=knowledge_category or "document",
            source="director_chat_upload",
            source_message_id=user_message.id,
        )

    response_text = f"Файл «{filename}» получен."
    if extracted_text:
        response_text += " Текст извлечен и доступен директору в контексте чата."
    elif detected_type == "image":
        response_text += " Изображение прикреплено к чату; при необходимости директор запросит уточнение или описание."
    elif extraction_error:
        response_text += f" Не удалось извлечь текст: {extraction_error}"

    if add_to_knowledge:
        response_text += " Файл также добавлен в базу знаний директора."
    else:
        response_text += " Можно загрузить его в базу знаний, если он должен использоваться в дальнейшей работе."

    director_message = DirectorChatMessage(
        user_id=current_user.id,
        message=response_text,
        message_type="knowledge" if add_to_knowledge else "text",
        message_direction="director",
        category="knowledge" if add_to_knowledge else "file",
        priority="P2",
        session_id=session_id,
        extra_data={
            "file": file_meta,
            "knowledge": knowledge_result.get("knowledge") if isinstance(knowledge_result, dict) else None,
        },
        status="completed",
        is_important=add_to_knowledge,
        parent_message_id=user_message.id,
    )
    db.add(director_message)
    await db.commit()
    await db.refresh(director_message)

    return {
        "user_message": user_message.to_dict(),
        "director_message": director_message.to_dict(),
        "file": file_meta,
        "knowledge": knowledge_result,
    }


@router.get("/greeting")
async def get_director_greeting(
    session_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Проактивное приветствие директора с текущей сводкой данных и активными задачами."""
    agent = DirectorAgent(db)
    result = await agent.get_greeting(
        user_id=current_user.id,
        session_id=session_id,
    )
    return result


@router.post("/tasks")
async def create_director_task(
    title: str = Body(..., embed=True),
    description: Optional[str] = Body(None, embed=True),
    priority: str = Body("P2", embed=True),
    source_message_id: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать задачу для AI-директора. Директор разобьёт её на подзадачи и определит нужных агентов."""
    agent = DirectorAgent(db)
    result = await agent.execute_task(
        user_id=current_user.id,
        task_title=title,
        task_description=description,
        priority=priority,
        source_message_id=UUID(source_message_id) if source_message_id else None,
    )
    return result


@router.get("/tasks")
async def list_director_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить список задач директора с фильтрацией."""
    conditions = [DirectorTask.user_id == current_user.id]
    if status:
        conditions.append(DirectorTask.status == status)
    if priority:
        conditions.append(DirectorTask.priority == priority)
    if task_type:
        conditions.append(DirectorTask.task_type == task_type)

    stmt = (
        select(DirectorTask)
        .where(and_(*conditions))
        .order_by(desc(DirectorTask.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return {"tasks": [_director_task_to_card(t) for t in tasks], "total": len(tasks)}


@router.get("/tasks/kanban")
async def get_director_tasks_kanban(
    board: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Канбан задач директора: объединяет director_tasks и agent_interaction_tasks."""
    director_result = await db.execute(
        select(DirectorTask)
        .where(DirectorTask.user_id == current_user.id)
        .order_by(desc(DirectorTask.created_at))
        .limit(limit)
    )
    director_cards = [_director_task_to_card(task) for task in director_result.scalars().all()]

    agent_result = await db.execute(
        select(AgentInteractionTask)
        .where(
            and_(
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
                AgentInteractionTask.task_type != "agent_control_chat",
            )
        )
        .order_by(desc(AgentInteractionTask.created_at))
        .limit(limit)
    )
    agent_cards = [_agent_task_to_director_card(task) for task in agent_result.scalars().all()]
    if board:
        agent_cards = [
            card for card in agent_cards
            if (card.get("extra_data") or {}).get("board") == board
        ]

    cards = sorted(
        director_cards + agent_cards,
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )[:limit]
    columns = [
        {"id": "todo", "title": "Нужно сделать", "cards": []},
        {"id": "in_progress", "title": "В работе", "cards": []},
        {"id": "done", "title": "Готово", "cards": []},
        {"id": "blocked", "title": "Блокеры / отменено", "cards": []},
    ]
    column_map = {column["id"]: column for column in columns}
    for card in cards:
        column_map[_kanban_column_for_status(card.get("status") or "pending")]["cards"].append(card)

    return {
        "columns": columns,
        "total": len(cards),
        "stats": {column["id"]: len(column["cards"]) for column in columns},
    }


@router.get("/activity")
async def get_director_work_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Лента хода работы: обращения к data tools и события межагентных задач."""
    events: list[dict] = []

    logs_result = await db.execute(
        select(AgentInteractionLog, AgentInteractionTask)
        .join(AgentInteractionTask, AgentInteractionTask.id == AgentInteractionLog.task_id)
        .where(
            and_(
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
                AgentInteractionTask.task_type != "agent_control_chat",
            )
        )
        .order_by(desc(AgentInteractionLog.created_at))
        .limit(limit)
    )
    for log, task in logs_result.all():
        title = (
            (task.input_data or {}).get("title")
            or (task.task_context or {}).get("title")
            or task.task_type.replace("_", " ")
        )
        events.append({
            "id": str(log.id),
            "kind": "agent",
            "title": log.message or log.event_type.replace("_", " "),
            "description": title,
            "source": task.source_agent,
            "target": task.target_agent,
            "status": task.status,
            "event_type": log.event_type,
            "task_id": str(task.id),
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "extra_data": {
                "event_data": log.event_data or {},
                "task_type": task.task_type,
                "href": f"/ai-marketer/tasks/{task.id}",
            },
        })

    data_messages_result = await db.execute(
        select(DirectorChatMessage)
        .where(
            DirectorChatMessage.user_id == current_user.id,
            DirectorChatMessage.message_direction == "director",
            DirectorChatMessage.extra_data.isnot(None),
        )
        .order_by(desc(DirectorChatMessage.created_at))
        .limit(limit)
    )
    for msg in data_messages_result.scalars().all():
        data_used = (msg.extra_data or {}).get("data_used") or []
        for tool_name in data_used:
            events.append({
                "id": f"{msg.id}:{tool_name}",
                "kind": "tool",
                "title": f"Директор запросил данные: {tool_name}",
                "description": "Данные использованы в ответе пользователю",
                "source": "director-agent",
                "target": tool_name,
                "status": "completed",
                "event_type": "data_tool_used",
                "task_id": None,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "extra_data": {"message_id": str(msg.id)},
            })

    events.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"activity": events[:limit], "total": len(events[:limit])}


@router.patch("/tasks/{source}/{task_id}/kanban")
async def move_director_task_card(
    source: str,
    task_id: UUID,
    column_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Переместить карточку канбана директора между колонками."""
    new_status = _status_for_kanban_column(source, column_id)

    if source == "director_task":
        result = await db.execute(
            select(DirectorTask).where(
                DirectorTask.id == task_id,
                DirectorTask.user_id == current_user.id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Задача директора не найдена")

        task.status = new_status
        if new_status == "completed" and not task.completed_at:
            task.completed_at = datetime.utcnow()
        elif new_status != "completed":
            task.completed_at = None

        await db.commit()
        await db.refresh(task)
        return {"task": _director_task_to_card(task)}

    if source != "agent_interaction":
        raise HTTPException(status_code=400, detail="Unknown task source")

    result = await db.execute(
        select(AgentInteractionTask).where(
            AgentInteractionTask.id == task_id,
            AgentInteractionTask.status != InteractionStatus.DELETED.value,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача агента не найдена")

    previous_status = task.status
    task.status = new_status
    if new_status == InteractionStatus.PROCESSING.value and not task.started_at:
        task.started_at = datetime.utcnow()
    if new_status == InteractionStatus.COMPLETED.value and not task.completed_at:
        task.completed_at = datetime.utcnow()
    elif new_status != InteractionStatus.COMPLETED.value:
        task.completed_at = None

    db.add(AgentInteractionLog(
        task_id=task.id,
        agent_name=f"director:{current_user.id}",
        event_type="kanban_card_moved",
        event_data={
            "before_status": previous_status,
            "after_status": new_status,
            "column_id": column_id,
        },
        message="Карточка перемещена на доске директора",
    ))
    await db.commit()
    await db.refresh(task)
    return {"task": _agent_task_to_director_card(task)}


def _task_action_message_text(action: str, card: dict, comment: Optional[str]) -> str:
    title = card.get("title") or "Задача"
    if action == "approved":
        return f"Задача «{title}» согласована и отправлена в работу."
    if action == "revision":
        suffix = f"\nКомментарий к доработке: {comment}" if comment else ""
        return f"Задача «{title}» отправлена на доработку.{suffix}"
    return f"Статус задачи «{title}» обновлён."


async def _post_task_action_to_chat(
    db: AsyncSession,
    user_id: UUID,
    session_id: Optional[str],
    action: str,
    card: dict,
    comment: Optional[str],
) -> DirectorChatMessage:
    msg = DirectorChatMessage(
        user_id=user_id,
        message=_task_action_message_text(action, card, comment),
        message_type="approval" if action in {"approved", "revision"} else "task",
        message_direction="director",
        category="task_control",
        priority=card.get("priority") or "P2",
        session_id=session_id,
        extra_data={
            "card_type": "task_action",
            "action": action,
            "comment": comment,
            "task": card,
        },
        status="completed",
        is_important=True,
    )
    db.add(msg)
    await db.flush()
    return msg


@router.post("/tasks/{source}/{task_id}/approve")
async def approve_director_chat_task(
    source: str,
    task_id: UUID,
    comment: Optional[str] = Body(None, embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Согласовать задачу из карточки в чате директора и записать событие в чат."""
    if source == "director_task":
        result = await db.execute(
            select(DirectorTask).where(
                DirectorTask.id == task_id,
                DirectorTask.user_id == current_user.id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Задача директора не найдена")
        task.status = "in_progress"
        task.extra_data = {
            **(task.extra_data or {}),
            "approval_status": "approved",
            "approval_comment": comment,
            "approved_at": datetime.utcnow().isoformat(),
        }
        card = _director_task_to_card(task)
    elif source == "agent_interaction":
        result = await db.execute(
            select(AgentInteractionTask).where(
                AgentInteractionTask.id == task_id,
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Задача агента не найдена")
        if task.status not in {
            InteractionStatus.PENDING_APPROVAL.value,
            InteractionStatus.VALIDATED.value,
            InteractionStatus.PENDING.value,
            InteractionStatus.APPROVED.value,
            InteractionStatus.QUEUED.value,
        }:
            raise HTTPException(status_code=400, detail="Задачу нельзя согласовать в текущем статусе")
        task.status = InteractionStatus.QUEUED.value
        task.updated_at = datetime.utcnow()
        task.input_data = {
            **(task.input_data or {}),
            "approval_status": "approved",
            "approval_comment": comment,
            "approved_at": datetime.utcnow().isoformat(),
        }
        db.add(AgentInteractionLog(
            task_id=task.id,
            agent_name=f"director:{current_user.id}",
            event_type="task_approved_from_director_chat",
            event_data={"comment": comment},
            message="Задача согласована из чата директора",
        ))
        card = _agent_task_to_director_card(task)
    else:
        raise HTTPException(status_code=400, detail="Unknown task source")

    chat_message = await _post_task_action_to_chat(
        db, current_user.id, session_id, "approved", card, comment
    )
    await db.commit()
    await db.refresh(chat_message)
    return {"task": card, "director_message": chat_message.to_dict()}


@router.post("/tasks/{source}/{task_id}/revise")
async def revise_director_chat_task(
    source: str,
    task_id: UUID,
    comment: Optional[str] = Body(None, embed=True),
    session_id: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отправить задачу на доработку из карточки в чате директора и записать событие в чат."""
    clean_comment = (comment or "").strip() or None

    if source == "director_task":
        result = await db.execute(
            select(DirectorTask).where(
                DirectorTask.id == task_id,
                DirectorTask.user_id == current_user.id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Задача директора не найдена")
        task.status = "pending"
        task.extra_data = {
            **(task.extra_data or {}),
            "approval_status": "needs_revision",
            "approval_comment": clean_comment,
            "revision_requested_at": datetime.utcnow().isoformat(),
        }
        card = _director_task_to_card(task)
    elif source == "agent_interaction":
        result = await db.execute(
            select(AgentInteractionTask).where(
                AgentInteractionTask.id == task_id,
                AgentInteractionTask.status != InteractionStatus.DELETED.value,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Задача агента не найдена")
        if task.status not in {
            InteractionStatus.PENDING_APPROVAL.value,
            InteractionStatus.VALIDATED.value,
            InteractionStatus.PENDING.value,
            InteractionStatus.APPROVED.value,
            InteractionStatus.QUEUED.value,
        }:
            raise HTTPException(status_code=400, detail="Задачу нельзя отправить на доработку в текущем статусе")
        task.status = InteractionStatus.PENDING.value
        task.updated_at = datetime.utcnow()
        task.input_data = {
            **(task.input_data or {}),
            "approval_status": "needs_revision",
            "approval_comment": clean_comment,
            "revision_requested_at": datetime.utcnow().isoformat(),
        }
        task.task_context = {**(task.task_context or {}), "revision_requested": True}
        db.add(AgentInteractionLog(
            task_id=task.id,
            agent_name=f"director:{current_user.id}",
            event_type="task_revision_requested_from_director_chat",
            event_data={"comment": clean_comment},
            message="Задача отправлена на доработку из чата директора",
        ))
        card = _agent_task_to_director_card(task)
    else:
        raise HTTPException(status_code=400, detail="Unknown task source")

    chat_message = await _post_task_action_to_chat(
        db, current_user.id, session_id, "revision", card, clean_comment
    )
    await db.commit()
    await db.refresh(chat_message)
    return {"task": card, "director_message": chat_message.to_dict()}


@router.get("/memory")
async def get_director_memory(
    memory_type: Optional[str] = Query(None, description="short_term, medium_term, long_term"),
    limit: int = Query(10, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить контекст памяти директора: кратковременная, среднесрочная, долгая."""
    agent = DirectorAgent(db)
    result = await agent.get_memory_context(
        user_id=current_user.id,
        memory_type=memory_type,
        limit=limit,
    )
    return result


@router.post("/knowledge")
async def add_director_knowledge(
    title: str = Body(...),
    content: str = Body(...),
    category: str = Body("fact"),
    source: Optional[str] = Body(None),
    source_message_id: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Добавить знание в базу знаний директора (долгая память).
    Знание автоматически векторизуется в Qdrant для семантического поиска.
    """
    agent = DirectorAgent(db)
    result = await agent.add_to_knowledge(
        user_id=current_user.id,
        title=title,
        content=content,
        category=category,
        source=source,
        source_message_id=UUID(source_message_id) if source_message_id else None,
    )
    return result


@router.get("/knowledge/search")
async def search_director_knowledge(
    query: str = Query(...),
    collection_name: str = Query("brand_philosophy", description="Коллекция Qdrant для поиска"),
    limit: int = Query(5, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Поиск по базе знаний (через Qdrant vector search по существующим документам)."""
    try:
        results = vector_service.get_context(collection_name, query, limit=limit)
        return {"results": results, "total": len(results), "collection": collection_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")


@router.get("/chat/search")
async def search_chat_history(
    query: str = Query(...),
    message_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Поиск по истории чата с AI-директором. Поддерживает текстовый поиск, фильтрацию по типу/категории/дате."""
    agent = DirectorAgent(db)
    result = await agent.search_chat(
        user_id=current_user.id,
        query=query,
        limit=limit,
        message_type=message_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )
    return result


@router.get("/chat/history")
async def get_chat_history(
    session_id: Optional[str] = Query(None),
    message_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить историю чата с AI-директором."""
    conditions = [
        DirectorChatMessage.user_id == current_user.id,
        DirectorChatMessage.status.in_(ACTIVE_CHAT_STATUSES),
    ]

    if session_id:
        conditions.append(DirectorChatMessage.session_id == session_id)
    if message_type:
        conditions.append(DirectorChatMessage.message_type == message_type)
    if category:
        conditions.append(DirectorChatMessage.category == category)

    stmt = (
        select(DirectorChatMessage)
        .where(and_(*conditions))
        .order_by(desc(DirectorChatMessage.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    # Считаем общее количество
    from sqlalchemy import func as sql_func
    count_stmt = select(sql_func.count()).select_from(
        select(DirectorChatMessage).where(and_(*conditions)).subquery()
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return {
        "messages": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/chat/history")
async def clear_chat_history(
    session_id: Optional[str] = Query(None),
    include_memory: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Очистить видимую историю чата с AI-директором без удаления задач и сегментов."""
    conditions = [
        DirectorChatMessage.user_id == current_user.id,
        DirectorChatMessage.status.in_(ACTIVE_CHAT_STATUSES),
    ]
    if session_id:
        conditions.append(DirectorChatMessage.session_id == session_id)

    ids_result = await db.execute(select(DirectorChatMessage.id).where(and_(*conditions)))
    message_ids = list(ids_result.scalars().all())
    deleted_count = len(message_ids)

    if message_ids:
        await db.execute(
            update(DirectorChatMessage)
            .where(DirectorChatMessage.id.in_(message_ids))
            .values(status="archived", updated_at=datetime.utcnow())
        )

    context_conditions = [
        DirectorConversationContext.user_id == current_user.id,
        DirectorConversationContext.status == "active",
    ]
    if session_id:
        context_conditions.append(DirectorConversationContext.session_id == session_id)
    context_result = await db.execute(
        update(DirectorConversationContext)
        .where(and_(*context_conditions))
        .values(status="expired", last_activity_at=datetime.utcnow())
    )

    archived_memory = 0
    archived_knowledge = 0
    if include_memory and message_ids:
        memory_result = await db.execute(
            update(DirectorMemory)
            .where(
                and_(
                    DirectorMemory.user_id == current_user.id,
                    DirectorMemory.source_message_id.in_(message_ids),
                    DirectorMemory.status == "active",
                )
            )
            .values(status="archived")
        )
        archived_memory = int(memory_result.rowcount or 0)

        knowledge_result = await db.execute(
            update(DirectorKnowledge)
            .where(
                and_(
                    DirectorKnowledge.user_id == current_user.id,
                    DirectorKnowledge.source_message_id.in_(message_ids),
                    DirectorKnowledge.source == "chat",
                    DirectorKnowledge.status == "active",
                )
            )
            .values(status="archived", updated_at=datetime.utcnow())
        )
        archived_knowledge = int(knowledge_result.rowcount or 0)

    await db.commit()

    return {
        "status": "cleared",
        "deleted_messages": deleted_count,
        "expired_contexts": int(context_result.rowcount or 0),
        "archived_memory": archived_memory,
        "archived_knowledge": archived_knowledge,
        "session_id": session_id,
    }


@router.get("/knowledge/list")
async def list_knowledge_base(
    category: Optional[str] = Query(None),
    collection_name: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить список документов в базе знаний. Читает из knowledge_documents (загруженные файлы)."""
    conditions = [KnowledgeDocument.status == "completed"]
    if category:
        conditions.append(KnowledgeDocument.file_type == category)
    if collection_name:
        conditions.append(KnowledgeDocument.collection_name == collection_name)

    stmt = (
        select(KnowledgeDocument)
        .where(and_(*conditions))
        .order_by(desc(KnowledgeDocument.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    knowledge_list = result.scalars().all()

    count_stmt = (
        select(sql_func.count())
        .select_from(select(KnowledgeDocument).where(and_(*conditions)).subquery())
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return {
        "knowledge": [
            {
                "id": str(k.id),
                "title": k.filename,
                "category": k.collection_name or k.file_type,
                "content": f"Файл: {k.filename}, тип: {k.file_type}, загружено элементов: {k.uploaded_items}/{k.total_items}",
                "content_type": k.file_type,
                "vector_id": None,
                "extra_data": {"collection_name": k.collection_name, "vector_document_ids": k.vector_document_ids},
                "source": k.source,
                "source_message_id": None,
                "source_task_id": None,
                "importance": 3,
                "usage_count": k.uploaded_items,
                "last_used_at": None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "updated_at": k.updated_at.isoformat() if k.updated_at else None,
                "status": k.status,
            }
            for k in knowledge_list
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/knowledge/{knowledge_id}")
async def delete_director_knowledge(
    knowledge_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить документ из базы знаний (полное удаление из БД и Qdrant)."""
    await _delete_document_by_id(db, knowledge_id)
    return {"status": "deleted", "knowledge_id": str(knowledge_id)}


# ───────────────────────────── DATA TOOLS ENDPOINTS ─────────────────────────────


@router.get("/data/today-sales")
async def data_today_sales(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Продажи за сегодня: выручка, количество заказов, товаров."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_today_sales()


@router.get("/data/sales-period")
async def data_sales_period(
    days: int = Query(7, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Продажи за N дней: заказы, выручка, средний чек, уникальные покупатели."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_sales_for_period(days)


@router.get("/data/sales-trend")
async def data_sales_trend(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ежедневный тренд продаж за N дней."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"trend": await service.get_daily_sales_trend(days)}


@router.get("/data/customer-summary")
async def data_customer_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Статистика покупателей: всего, по сегментам, новые, баллы лояльности."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_customer_summary()


@router.get("/data/product-summary")
async def data_product_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Статистика товаров: всего активных, core assortment, по категориям, по брендам."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_product_summary()


@router.get("/data/top-products")
async def data_top_products(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Топ продаваемых товаров."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"products": await service.get_top_selling_products(limit)}


@router.get("/data/customers/search")
async def data_customers_search(
    query: str = Query(..., min_length=1),
    search_by: str = Query("auto", regex="^(auto|card|email|phone|name)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Поиск покупателей по discount_card, email, phone, имени."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"customers": await service.find_customer(query, search_by)}


@router.get("/data/customers/{customer_id}/purchases")
async def data_customer_purchases(
    customer_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История покупок конкретного покупателя."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_customer_purchase_history(customer_id, limit)


@router.get("/data/stores")
async def data_stores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список магазинов с продажами."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"stores": await service.get_stores_summary()}


@router.get("/data/campaigns")
async def data_campaigns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Активные маркетинговые кампании."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"campaigns": await service.get_active_campaigns()}


@router.get("/data/recent-orders")
async def data_recent_orders(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Последние заказы (статус, сумма, покупатель)."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return {"orders": await service.get_recent_orders(limit)}


@router.get("/data/general-stats")
async def data_general_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Общая сводка всех метрик: продажи сегодня, неделя, покупатели, товары."""
    from app.agents.director_data_service import DirectorDataService
    service = DirectorDataService(db)
    return await service.get_general_stats()
