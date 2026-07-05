"""
API endpoints для генерации персональных сообщений клиентам
"""
import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete, distinct, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
import asyncio
import tempfile
import uuid
import time
from uuid import UUID
from uuid import UUID
import os
from app.database.connection import get_db
from app.agents.communication_agent import CommunicationAgent
from app.services.communication_service import CommunicationService
from app.services.sms_service import get_sms_service
from app.services.generation_history import get_generation_history
from app.models.user import User
from app.models.customer_message import CustomerMessage
from collections import defaultdict

logger = logging.getLogger(__name__)

router = APIRouter()

_BATCH_MSG_ID_NAMESPACE = uuid.UUID("6d986d5d-70ac-4b09-9fdc-dc0e63f5501e")
_CUSTOMER_MESSAGES_CACHE: Dict[str, Tuple[float, "CustomerMessagesListResponse"]] = {}
_CUSTOMER_MESSAGES_CACHE_TTL_SECONDS = 15.0
_GENERATED_MESSAGES_SYNC_FILE_MTIME_NS: Dict[str, int] = {}
_GENERATED_MESSAGES_SYNC_DEFAULT_INTERVAL_SECONDS = 10.0
COMMUNICATION_BATCH_MAX_LLM_MESSAGES = int(os.getenv("COMMUNICATION_BATCH_MAX_LLM_MESSAGES", "500"))
COMMUNICATION_BATCH_MAX_CONSECUTIVE_ERRORS = int(os.getenv("COMMUNICATION_BATCH_MAX_CONSECUTIVE_ERRORS", "5"))


def _deterministic_batch_message_id(generation_id: str, user_id: UUID) -> uuid.UUID:
    return uuid.uuid5(_BATCH_MSG_ID_NAMESPACE, f"{generation_id}:{str(user_id)}")


async def _persist_generated_messages(
    db: AsyncSession,
    *,
    messages: List[Dict[str, Any]],
    message_kind: str,
    generation_id: Optional[str],
    default_event_type: Optional[str],
    default_event_brand: Optional[str],
    default_event_store: Optional[str],
    commit: bool = True,
):
    rows: List[Dict[str, Any]] = []
    for msg in messages:
        client_id_raw = msg.get("client_id") if isinstance(msg, dict) else None
        if not client_id_raw:
            continue
        try:
            client_uuid = UUID(str(client_id_raw))
        except Exception:
            continue

        payload: Dict[str, Any] = dict(msg) if isinstance(msg, dict) else {}
        payload["message_kind"] = message_kind
        if generation_id:
            payload["generation_id"] = generation_id

        row: Dict[str, Any] = {
            "id": _deterministic_batch_message_id(generation_id or "no-generation", client_uuid)
            if message_kind == "broadcast"
            else uuid.uuid4(),
            "user_id": client_uuid,
            "message": payload.get("message") or "",
            "cta": payload.get("cta"),
            "segment": payload.get("segment"),
            "event_type": payload.get("event_type") or default_event_type,
            "event_brand": payload.get("brand") or payload.get("event_brand") or default_event_brand,
            "event_store": payload.get("store") or payload.get("event_store") or default_event_store,
            "payload": payload,
            "status": "new",
        }
        if row["message"]:
            rows.append(row)

    if not rows:
        return

    stmt = pg_insert(CustomerMessage).values(rows).on_conflict_do_nothing(index_elements=["id"])
    await db.execute(stmt)
    if commit:
        await db.commit()


def _generated_messages_base_dir() -> Path:
    project_root = Path(__file__).parent.parent.parent
    return project_root / "backend" / "generated_messages"


def _extract_generation_id_from_filename(filename: str) -> Optional[str]:
    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.json$", filename)
    if not m:
        return None
    return m.group(1)


async def _safe_read_json_with_retries(filepath: Path, attempts: int = 3, delay: float = 0.25) -> Dict[str, Any]:
    last_err = None
    for _ in range(attempts):
        try:
            raw = await asyncio.to_thread(filepath.read_text, encoding="utf-8")
            return {"success": True, "data": json.loads(raw), "error": None}
        except Exception as e:
            last_err = str(e)
            await asyncio.sleep(delay)
    return {"success": False, "data": None, "error": last_err or "unknown error"}


async def _delete_messages_by_generation_ids(db: AsyncSession, generation_ids: List[str]) -> List[UUID]:
    gen_ids = [g for g in (generation_ids or []) if isinstance(g, str) and g]
    if not gen_ids:
        return []
    stmt = (
        delete(CustomerMessage)
        .where(CustomerMessage.payload["generation_id"].astext.in_(gen_ids))
        .returning(CustomerMessage.user_id)
    )
    res = await db.execute(stmt)
    rows = res.fetchall()
    return [r[0] for r in rows if r and r[0]]


async def _sync_generated_messages_with_db(db: AsyncSession) -> Dict[str, Any]:
    history = get_generation_history()
    base_dir = _generated_messages_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    imported_files: int = 0
    imported_messages: int = 0
    deleted_generations: int = 0
    deleted_messages: int = 0
    failed_files: Dict[str, str] = {}

    generation_ids_in_files: set[str] = set()

    for p in sorted(base_dir.glob("messages_*.json")):
        if p.name == "history.jsonl":
            continue
        gen_id = _extract_generation_id_from_filename(p.name)
        if not gen_id:
            continue
        generation_ids_in_files.add(gen_id)

        try:
            st = await asyncio.to_thread(p.stat)
            prev_mtime = _GENERATED_MESSAGES_SYNC_FILE_MTIME_NS.get(str(p))
            if prev_mtime is not None and prev_mtime == getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)):
                continue
        except Exception:
            pass

        read_res = await _safe_read_json_with_retries(p, attempts=4, delay=0.25)
        if not read_res["success"]:
            failed_files[str(p)] = f"read_error: {read_res['error']}"
            continue
        raw = read_res["data"]
        messages: Any
        if isinstance(raw, dict) and "messages" in raw:
            messages = raw.get("messages") or []
        else:
            messages = raw or []
        if not isinstance(messages, list):
            failed_files[str(p)] = "invalid_structure"
            continue

        rec = await history.get(gen_id)
        default_event_type = rec.get("event_type") if isinstance(rec, dict) else None

        try:
            async with db.begin():
                await _persist_generated_messages(
                    db,
                    messages=messages,
                    message_kind="broadcast",
                    generation_id=gen_id,
                    default_event_type=default_event_type,
                    default_event_brand=None,
                    default_event_store=None,
                    commit=False,
                )
        except Exception as e:
            failed_files[str(p)] = f"db_error: {e}"
            continue

        imported_files += 1
        imported_messages += len(messages)
        try:
            st = await asyncio.to_thread(p.stat)
            _GENERATED_MESSAGES_SYNC_FILE_MTIME_NS[str(p)] = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        except Exception:
            _GENERATED_MESSAGES_SYNC_FILE_MTIME_NS[str(p)] = int(time.time() * 1e9)

        for m in messages[:200]:
            client_id_raw = m.get("client_id") if isinstance(m, dict) else None
            if client_id_raw:
                try:
                    _invalidate_customer_messages_cache(UUID(str(client_id_raw)))
                except Exception:
                    pass

    try:
        db_gen_ids_res = await db.execute(
            select(distinct(CustomerMessage.payload["generation_id"].astext)).where(
                CustomerMessage.payload["generation_id"].astext.isnot(None)
            )
        )
        db_gen_ids = {row[0] for row in db_gen_ids_res.all() if row and row[0]}
        missing_in_fs = sorted(list(db_gen_ids - generation_ids_in_files))
        if missing_in_fs:
            async with db.begin():
                deleted_user_ids = await _delete_messages_by_generation_ids(db, missing_in_fs)
            deleted_generations = len(missing_in_fs)
            deleted_messages = len(deleted_user_ids)
            for uid in deleted_user_ids[:500]:
                try:
                    _invalidate_customer_messages_cache(uid)
                except Exception:
                    pass
    except Exception as e:
        logger.exception(f"Ошибка обратной синхронизации (удаление из БД): {e}")

    result = {
        "imported_files": imported_files,
        "imported_messages": imported_messages,
        "deleted_generations": deleted_generations,
        "deleted_messages": deleted_messages,
        "failed_files": failed_files,
    }
    logger.info(f"Синхронизация generated_messages ↔ БД: {result}")
    return result


async def _generated_messages_sync_loop(stop_event: asyncio.Event, interval_seconds: float):
    from app.database.connection import AsyncSessionLocal

    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as db:
                await _sync_generated_messages_with_db(db)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"Ошибка цикла синхронизации generated_messages: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def start_generated_messages_sync(app, interval_seconds: Optional[float] = None):
    if getattr(app.state, "generated_messages_sync_task", None):
        return
    stop_event = asyncio.Event()
    interval = interval_seconds or _GENERATED_MESSAGES_SYNC_DEFAULT_INTERVAL_SECONDS
    task = asyncio.create_task(_generated_messages_sync_loop(stop_event, interval))
    app.state.generated_messages_sync_stop_event = stop_event
    app.state.generated_messages_sync_task = task


async def stop_generated_messages_sync(app):
    stop_event = getattr(app.state, "generated_messages_sync_stop_event", None)
    task = getattr(app.state, "generated_messages_sync_task", None)
    if stop_event:
        stop_event.set()
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass


def _invalidate_customer_messages_cache(customer_id: UUID):
    prefix = f"{str(customer_id)}:"
    for k in list(_CUSTOMER_MESSAGES_CACHE.keys()):
        if k.startswith(prefix):
            _CUSTOMER_MESSAGES_CACHE.pop(k, None)


def _parse_dt(value: str, *, end_of_day: bool) -> Optional[datetime]:
    if not value:
        return None
    v = value.strip()
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        d = datetime.strptime(v, "%Y-%m-%d").date()
        if end_of_day:
            return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    except Exception:
        return None


def _infer_message_kind(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "individual"
    kind = payload.get("message_kind")
    if kind in {"individual", "broadcast"}:
        return kind
    if payload.get("generation_id"):
        return "broadcast"
    return "individual"


def _extract_generation_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    gen_id = payload.get("generation_id")
    if isinstance(gen_id, str) and gen_id:
        return gen_id
    return None


async def _run_batch_generate_task(rec_id: str, request_data: Dict[str, Any]):
    """
    Фоновая задача батч-генерации.
    Использует отдельную сессию БД и обновляет GenerationHistory.
    """
    from app.database.connection import AsyncSessionLocal

    history = get_generation_history()
    try:
        request = BatchGenerateRequest(**request_data)
    except Exception as e:
        logger.exception(f"Invalid batch request for background task {rec_id}: {e}")
        await history.fail(rec_id, f"Invalid request: {e}")
        return

    async with AsyncSessionLocal() as db:
        try:
            service = CommunicationService(db)
            agent = CommunicationAgent(db)

            event_dict = {
                "type": request.event.type,
                "brand": request.event.brand or request.brand,
                "store": None if request.auto_detect_store else request.event.store,
                "auto_detect_store": request.auto_detect_store,
                **(request.event.metadata or {}),
            }

            search_criteria_dict = request.search_criteria.dict(exclude_none=True) if request.search_criteria else None

            seg_name = None
            seg_id = None
            if search_criteria_dict:
                seg_name = search_criteria_dict.get("segment_name")
                seg_id = search_criteria_dict.get("segment_id")

            segment_client_ids = None
            try:
                from app.models.customer_segment import CustomerSegment
                from app.models.user_segment import UserSegment
                from app.models.user import User as UserModel
                from app.api.customer_segmentation import _build_select_for_rules

                seg_uuid = None
                seg_obj = None
                if seg_id:
                    try:
                        seg_uuid = UUID(seg_id)
                    except Exception:
                        await history.fail(rec_id, "Некорректный формат segment_id (UUID).")
                        return
                    seg_row = await db.execute(
                        select(CustomerSegment).where(
                            CustomerSegment.id == seg_uuid,
                            CustomerSegment.is_active == True,
                        )
                    )
                    seg_obj = seg_row.scalar_one_or_none()
                    if not seg_obj:
                        await history.fail(rec_id, f"Сегмент '{seg_id}' не найден или не активен.")
                        return
                if not seg_uuid and seg_name:
                    seg_row = await db.execute(
                        select(CustomerSegment).where(
                            CustomerSegment.name == seg_name,
                            CustomerSegment.is_active == True,
                        )
                    )
                    seg_obj = seg_row.scalar_one_or_none()
                    if not seg_obj:
                        await history.fail(rec_id, f"Сегмент '{seg_name}' не найден или не активен.")
                        return
                    seg_uuid = seg_obj.id

                if seg_uuid:
                    seg_users_stmt = (
                        select(UserSegment.user_id)
                        .join(UserModel, UserModel.id == UserSegment.user_id)
                        .where(
                            UserSegment.segment_id == seg_uuid,
                            UserModel.is_customer == True,
                        )
                        .limit(request.limit or 1000)
                    )
                    seg_users_result = await db.execute(seg_users_stmt)
                    segment_client_ids = [row[0] for row in seg_users_result.all()]
                    if not segment_client_ids and seg_obj is not None:
                        rules = seg_obj.rules if isinstance(seg_obj.rules, dict) else {}
                        stmt, _ = _build_select_for_rules(rules or {})
                        subq = stmt.subquery()
                        seg_users_by_rules_stmt = (
                            select(UserModel.id)
                            .where(
                                UserModel.id.in_(select(subq.c.id)),
                                UserModel.is_customer == True,
                            )
                            .limit(request.limit or 1000)
                        )
                        seg_users_by_rules_result = await db.execute(seg_users_by_rules_stmt)
                        segment_client_ids = list(seg_users_by_rules_result.scalars().all())
                    logger.info(f"[async] Segment '{seg_name or seg_id}': loaded {len(segment_client_ids)} users (pre-limit).")
            except Exception as seg_err:
                logger.exception(f"[async] Ошибка при загрузке пользователей сегмента: {seg_err}")
                await history.fail(rec_id, "Не удалось прочитать пользователей сегмента.")
                return

            client_ids: List[UUID] = []
            if request.client_ids:
                for client_id_str in request.client_ids:
                    try:
                        client_ids.append(UUID(client_id_str))
                    except ValueError:
                        logger.warning(f"[async] Invalid client_id: {client_id_str}")

            use_selected_segment_as_audience = (
                request.event.type == "brand_arrival"
                and segment_client_ids is not None
                and len(segment_client_ids) > 0
            )

            if use_selected_segment_as_audience:
                client_ids = [UUID(str(cid)) for cid in segment_client_ids]
                logger.info(
                    "[async] Using selected segment as brand_arrival audience for rec_id=%s: %s clients. "
                    "Brand is used as event context, not as an extra purchase-history filter.",
                    rec_id,
                    len(client_ids),
                )
            elif request.brand:
                client_ids = await service.find_clients_by_brand(
                    request.brand,
                    limit=request.limit or 100,
                    search_criteria=search_criteria_dict,
                )
            elif request.event.type:
                client_ids = await service.find_clients_for_event(
                    request.event.type,
                    event_data=event_dict,
                    limit=request.limit or 100,
                    search_criteria=search_criteria_dict,
                )
            else:
                await history.fail(rec_id, "Не указан тип события (event.type).")
                return

            if segment_client_ids is not None and not use_selected_segment_as_audience:
                seg_set = {UUID(str(cid)) for cid in segment_client_ids}
                if client_ids:
                    client_ids = [cid for cid in client_ids if cid in seg_set]
                else:
                    client_ids = list(seg_set)

            requested_limit = request.limit or 100
            lim = min(requested_limit, COMMUNICATION_BATCH_MAX_LLM_MESSAGES)
            if requested_limit > lim:
                logger.warning(
                    "[async] Batch generation limit capped from %s to %s for rec_id=%s. "
                    "Use COMMUNICATION_BATCH_MAX_LLM_MESSAGES to change preview batch size.",
                    requested_limit,
                    lim,
                    rec_id,
                )
            client_ids = client_ids[:lim]

            await history.set_total(rec_id, len(client_ids))

            if not client_ids:
                from app.models.user import User

                debug_info = {
                    "event_type": request.event.type,
                    "has_brand": bool(request.brand or request.event.brand),
                    "brand": request.brand or request.event.brand,
                    "has_client_ids": bool(request.client_ids),
                    "client_ids_count": len(request.client_ids) if request.client_ids else 0,
                    "limit": lim,
                    "segment": seg_name or seg_id,
                    "segment_users_count": len(segment_client_ids or []),
                }

                total_customers_result = await db.execute(
                    select(func.count(User.id)).where(User.is_customer == True)
                )
                total_customers = total_customers_result.scalar() or 0

                error_message = "Клиенты не найдены для указанных критериев"
                if request.event.type == "brand_arrival" and (request.brand or request.event.brand):
                    error_message = f"Клиенты с брендом '{request.brand or request.event.brand}' не найдены в истории покупок"
                elif total_customers == 0:
                    error_message = "В базе данных нет клиентов. Выполните синхронизацию с 1С."
                elif request.event.type == "no_purchase_180":
                    error_message = "Клиенты без покупок более 180 дней не найдены"
                elif request.event.type == "bonus_balance":
                    error_message = "Клиенты с балансом бонусов не найдены"
                elif seg_name or seg_id:
                    seg_label = seg_name or seg_id
                    error_message = f"В сегменте «{seg_label}» не найдено клиентов, соответствующих выбранному событию и критериям"

                response_data = {
                    "status": "success",
                    "messages": [],
                    "count": 0,
                    "message": error_message,
                    "debug_info": debug_info,
                    "total_customers_in_db": total_customers,
                }
                saved_file = await _write_generation_result_file(rec_id, request.event.type, response_data)
                await history.complete(rec_id, saved_file=saved_file, result=response_data)
                logger.info(f"[async] No clients for generation {rec_id}: {debug_info}")
                return

            messages: List[Dict[str, Any]] = []
            errors: List[Dict[str, Any]] = []
            total_clients = len(client_ids)

            logger.info(f"[async] Starting batch generation for {total_clients} clients (rec_id={rec_id})")

            consecutive_errors = 0
            for idx, client_id in enumerate(client_ids, 1):
                try:
                    if idx <= 5 or idx % 10 == 0 or idx == total_clients:
                        logger.info(f"[async] Processing client {idx}/{total_clients}: {client_id}")

                    client_data = await service.get_client_data(client_id)
                    if not client_data:
                        logger.warning(f"[async] Client data not found for {client_id}")
                        continue

                    message = await agent.generate_message(
                        client_id=client_id,
                        event=event_dict,
                        client_data=client_data,
                        max_length=request.max_length
                    )

                    if isinstance(message, dict):
                        messages.append(message)
                    else:
                        messages.append({
                            "client_id": str(getattr(message, "client_id", "")),
                            "phone": getattr(message, "phone", None),
                            "name": getattr(message, "name", None),
                            "gender": getattr(message, "gender", None),
                            "segment": getattr(message, "segment", ""),
                            "reason": getattr(message, "reason", ""),
                            "message": getattr(message, "message", ""),
                            "cta": getattr(message, "cta", ""),
                            "brand": getattr(message, "brand", None),
                            "store": getattr(message, "store", None),
                        })

                    consecutive_errors = 0
                    await history.update_progress(rec_id, processed=idx, success=len(messages), errors=len(errors))
                except Exception as e:
                    logger.warning(f"[async] Failed to generate message for client {client_id} ({idx}/{total_clients}): {e}")
                    errors.append({
                        "client_id": str(client_id),
                        "error": str(e),
                    })
                    consecutive_errors += 1
                    await history.update_progress(rec_id, processed=idx, success=len(messages), errors=len(errors))
                    if consecutive_errors >= COMMUNICATION_BATCH_MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            "[async] Aborting batch generation rec_id=%s after %s consecutive errors",
                            rec_id,
                            consecutive_errors,
                        )
                        break

            logger.info(f"[async] Batch generation completed for rec_id={rec_id}: {len(messages)} messages, {len(errors)} errors")

            try:
                await _persist_generated_messages(
                    db,
                    messages=messages,
                    message_kind="broadcast",
                    generation_id=rec_id,
                    default_event_type=request.event.type,
                    default_event_brand=request.event.brand or request.brand,
                    default_event_store=request.event.store,
                )
                for m in messages[:20]:
                    client_id_raw = m.get("client_id") if isinstance(m, dict) else None
                    if client_id_raw:
                        try:
                            _invalidate_customer_messages_cache(UUID(str(client_id_raw)))
                        except Exception:
                            pass
            except Exception as persist_err:
                logger.exception(f"[async] Не удалось сохранить сообщения в историю для rec_id={rec_id}: {persist_err}")
                await db.rollback()
                await history.fail(rec_id, "Не удалось сохранить сообщения в историю пользователя.")
                return

            project_root = Path(__file__).parent.parent.parent
            save_dir = project_root / "backend" / "generated_messages"
            event_type = request.event.type or "unknown"
            safe_event_type = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in event_type)
            # Фиксируем имя файла по идентификатору генерации, чтобы избежать дублей
            filename = f"messages_{safe_event_type}_{rec_id}.json"
            filepath = save_dir / filename

            response_data = {
                "status": "success",
                "messages": messages,
                "count": len(messages),
                "errors": errors or None,
            }

            write_res = await _safe_write_json_with_retries(filepath, response_data, attempts=5, delay=0.4)
            if not write_res.get("success"):
                err = write_res.get("error") or "unknown error"
                logger.error(f"[async] Ошибка записи JSON файла {filepath}: {err}")
                await history.fail(rec_id, f"Ошибка записи файла: {err}")
            else:
                logger.info(f"[async] ✅ Сохранено {len(messages)} сообщений в файл: {filepath}")
                await history.complete(rec_id, saved_file=str(filepath), result={
                    "status": "success",
                    "count": len(messages),
                    "errors": len(errors),
                })
        except Exception as e:
            logger.exception(f"[async] Unexpected error in batch generation task {rec_id}: {e}")
            try:
                await history.fail(rec_id, str(e))
            except Exception:
                logger.exception(f"[async] Не удалось обновить статус истории для задачи {rec_id}")


async def _safe_write_json_with_retries(filepath: Path, payload: Dict[str, Any], attempts: int = 3, delay: float = 0.5) -> Dict[str, Any]:
    """
    Безопасная асинхронная запись JSON с ретраями и атомарной заменой.
    Возвращает словарь с полями {success: bool, error: Optional[str]}
    """
    import json
    try:
        directory = filepath.parent
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"success": False, "error": f"Failed to ensure directory: {e}"}
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            # Пишем во временный файл и переименовываем
            def _write():
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(directory), delete=False) as tmp:
                    json.dump(payload, tmp, ensure_ascii=False, indent=2, default=str)
                    tmp.flush()
                    return tmp.name
            tmp_path = await asyncio.to_thread(_write)
            await asyncio.to_thread(Path(tmp_path).replace, filepath)
            return {"success": True, "error": None}
        except Exception as e:
            last_err = str(e)
            await asyncio.sleep(delay)
    return {"success": False, "error": last_err or "unknown error"}


async def _write_generation_result_file(rec_id: str, event_type: Optional[str], response_data: Dict[str, Any]) -> Optional[str]:
    project_root = Path(__file__).parent.parent.parent
    save_dir = project_root / "backend" / "generated_messages"
    safe_event_type = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in (event_type or "unknown"))
    filepath = save_dir / f"messages_{safe_event_type}_{rec_id}.json"
    write_res = await _safe_write_json_with_retries(filepath, response_data, attempts=5, delay=0.4)
    if not write_res.get("success"):
        logger.error("Не удалось записать файл результата генерации %s: %s", rec_id, write_res.get("error"))
        return None
    return str(filepath)


class EventData(BaseModel):
    """Данные события"""
    type: str  # brand_arrival, loyalty_level_up, bonus_balance, no_purchase_180, holiday_male
    brand: Optional[str] = None
    store: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GenerateMessageRequest(BaseModel):
    """Запрос на генерацию сообщения"""
    client_id: str
    event: EventData


class GenerateMessageResponse(BaseModel):
    """Ответ с сгенерированным сообщением"""
    client_id: str
    phone: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None  # "male", "female" или None
    segment: str
    reason: str
    message: str
    cta: str
    brand: Optional[str] = None
    store: Optional[str] = None


class CustomerMessageItem(BaseModel):
    """Элемент списка сообщений покупателя"""
    id: str
    message: str
    cta: Optional[str] = None
    segment: Optional[str] = None
    event_type: Optional[str] = None
    event_brand: Optional[str] = None
    event_store: Optional[str] = None
    message_kind: str  # individual|broadcast
    generation_id: Optional[str] = None
    status: str  # new, sent
    sent_at: Optional[datetime] = None
    created_at: datetime


class CustomerMessagesListResponse(BaseModel):
    """Список сообщений покупателя"""
    items: List[CustomerMessageItem]
    total: int


class SearchCriteria(BaseModel):
    """Критерии поиска клиентов"""
    # Фильтры по сегментам
    segments: Optional[List[str]] = None  # Список сегментов для фильтрации (A, B, C, D, E)
    segment_name: Optional[str] = None    # Название сегмента из CustomerSegment (например, "Лояльные покупатели")
    segment_id: Optional[str] = None      # ID сегмента (UUID из CustomerSegment)
    
    # Фильтры по полу
    gender: Optional[str] = None  # "male", "female" или None (все)
    
    # Фильтры по метрикам
    min_total_spend_365: Optional[int] = None  # Минимальная сумма покупок за 365 дней (в копейках)
    max_total_spend_365: Optional[int] = None  # Максимальная сумма покупок за 365 дней
    min_purchases_365: Optional[int] = None  # Минимальное количество покупок за 365 дней
    max_purchases_365: Optional[int] = None  # Максимальное количество покупок за 365 дней
    
    # Фильтры по датам
    min_days_since_last: Optional[int] = None  # Минимальное количество дней с последней покупки
    max_days_since_last: Optional[int] = None  # Максимальное количество дней с последней покупки
    
    # Фильтры по бонусам
    min_bonus_balance: Optional[int] = None  # Минимальный баланс бонусов
    max_bonus_balance: Optional[int] = None  # Максимальный баланс бонусов
    
    # Фильтры по местоположению
    is_local_only: Optional[bool] = None  # Только местные клиенты
    cities: Optional[List[str]] = None  # Список городов для фильтрации
    
    # Фильтры по брендам
    must_have_brands: Optional[List[str]] = None  # Клиенты должны иметь хотя бы один из этих брендов
    exclude_brands: Optional[List[str]] = None  # Исключить клиентов с этими брендами


class BatchGenerateRequest(BaseModel):
    """Запрос на батч-генерацию сообщений"""
    event: EventData
    client_ids: Optional[List[str]] = None
    brand: Optional[str] = None  # Если указан, найдет клиентов с этим брендом
    limit: Optional[int] = 100
    max_length: Optional[int] = None  # Максимальная длина сообщения в символах
    search_criteria: Optional[SearchCriteria] = None  # Дополнительные критерии поиска
    auto_detect_store: Optional[bool] = False  # Автоматическое определение бутика из истории покупок или города


class BatchGenerateAsyncResponse(BaseModel):
    status: str
    generation_id: str
    events_url: str


@router.post("/sync-generated-messages")
async def trigger_generated_messages_sync(db: AsyncSession = Depends(get_db)):
    """Запустить ручную синхронизацию generated_messages ↔ БД"""
    return await _sync_generated_messages_with_db(db)


@router.post("/generate-message", response_model=GenerateMessageResponse)
async def generate_message(
    request: GenerateMessageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Генерация персонального сообщения для клиента
    
    Входные данные:
    - client_id: UUID клиента
    - event: Событие (type, brand, store)
    
    Возвращает:
    - segment: Сегмент клиента (A-E)
    - message: Текст сообщения
    - cta: Призыв к действию
    - brand, store: Бренд и магазин (если применимо)
    """
    try:
        # Парсим UUID
        try:
            client_uuid = UUID(request.client_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid client_id format: {request.client_id}")
        
        # Создаем агент и сервис
        agent = CommunicationAgent(db)
        
        # Формируем event dict
        event_dict = {
            "type": request.event.type,
            "brand": request.event.brand,
            "store": request.event.store,
            **(request.event.metadata or {})
        }
        
        # Генерируем сообщение
        result = await agent.generate_message(
            client_id=client_uuid,
            event=event_dict
        )
        
        # Сохраняем в БД для истории и управления
        msg = CustomerMessage(
            user_id=client_uuid,
            message=result["message"],
            cta=result.get("cta"),
            segment=result.get("segment"),
            event_type=request.event.type,
            event_brand=request.event.brand,
            event_store=request.event.store,
            payload={**result, "message_kind": "individual"},
            status="new",
        )
        db.add(msg)
        await db.commit()
        _invalidate_customer_messages_cache(client_uuid)
        
        return GenerateMessageResponse(**result)
    
    except ValueError as e:
        logger.warning(f"Value error generating message: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error generating message: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating message: {str(e)}")


@router.get("/customers/{customer_id}/messages", response_model=CustomerMessagesListResponse)
async def list_customer_messages(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    kind: str = Query("all"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    desc: bool = Query(True),
):
    """Список сгенерированных сообщений для покупателя (история общения)."""
    cache_key = f"{str(customer_id)}:{kind}:{date_from or ''}:{date_to or ''}:{sort_by}:{'desc' if desc else 'asc'}:{limit}:{offset}"
    now_ts = time.time()
    cached = _CUSTOMER_MESSAGES_CACHE.get(cache_key)
    if cached and (now_ts - cached[0]) < _CUSTOMER_MESSAGES_CACHE_TTL_SECONDS:
        return cached[1]

    dt_from = _parse_dt(date_from, end_of_day=False) if date_from else None
    dt_to = _parse_dt(date_to, end_of_day=True) if date_to else None

    conditions = [CustomerMessage.user_id == customer_id]
    if dt_from:
        conditions.append(CustomerMessage.created_at >= dt_from)
    if dt_to:
        conditions.append(CustomerMessage.created_at <= dt_to)
    if kind == "broadcast":
        conditions.append(
            and_(
                CustomerMessage.payload.isnot(None),
                or_(
                    CustomerMessage.payload["message_kind"].astext == "broadcast",
                    CustomerMessage.payload.has_key("generation_id"),
                ),
            )
        )
    elif kind == "individual":
        conditions.append(
            or_(
                CustomerMessage.payload.is_(None),
                CustomerMessage.payload["message_kind"].astext == "individual",
                and_(
                    CustomerMessage.payload.isnot(None),
                    ~CustomerMessage.payload.has_key("generation_id"),
                    CustomerMessage.payload["message_kind"].astext.is_(None),
                ),
            )
        )

    sort_cols = {
        "created_at": CustomerMessage.created_at,
        "sent_at": CustomerMessage.sent_at,
        "status": CustomerMessage.status,
    }
    sort_col = sort_cols.get(sort_by, CustomerMessage.created_at)
    order_by_expr = sort_col.desc() if desc else sort_col.asc()

    result = await db.execute(
        select(CustomerMessage)
        .where(and_(*conditions))
        .order_by(order_by_expr)
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()
    count_result = await db.execute(
        select(func.count()).select_from(CustomerMessage).where(and_(*conditions))
    )
    total = count_result.scalar() or 0
    items = [
        CustomerMessageItem(
            id=str(m.id),
            message=m.message,
            cta=m.cta,
            segment=m.segment,
            event_type=m.event_type,
            event_brand=m.event_brand,
            event_store=m.event_store,
            message_kind=_infer_message_kind(m.payload),
            generation_id=_extract_generation_id(m.payload),
            status=m.status,
            sent_at=m.sent_at,
            created_at=m.created_at,
        )
        for m in messages
    ]
    resp = CustomerMessagesListResponse(items=items, total=total)
    _CUSTOMER_MESSAGES_CACHE[cache_key] = (now_ts, resp)
    return resp


@router.delete("/messages/{message_id}")
async def delete_customer_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Удалить сообщение из истории."""
    result = await db.execute(select(CustomerMessage).where(CustomerMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    customer_id = msg.user_id
    db.delete(msg)
    await db.commit()
    _invalidate_customer_messages_cache(customer_id)
    return {"status": "ok", "message": "Сообщение удалено"}


@router.post("/messages/{message_id}/send")
async def mark_message_sent(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Отметить сообщение как отправленное (с датой отправки)."""
    result = await db.execute(select(CustomerMessage).where(CustomerMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    msg.status = "sent"
    msg.sent_at = datetime.now(timezone.utc)
    await db.commit()
    _invalidate_customer_messages_cache(msg.user_id)
    return {
        "status": "ok",
        "message": "Сообщение отмечено как отправленное",
        "sent_at": msg.sent_at.isoformat(),
    }


@router.post("/batch-generate", response_model=None)  # Явно указываем, что не используем модель
async def batch_generate_messages(
    request: BatchGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Батч-генерация сообщений для нескольких клиентов
    
    Можно указать:
    - client_ids: Список конкретных клиентов
    - brand: Найти всех клиентов с этим брендом в истории
    - event.type: Тип события для автоматического поиска клиентов
    
    Возвращает список сгенерированных сообщений
    """
    try:
        service = CommunicationService(db)
        agent = CommunicationAgent(db)
        history = get_generation_history()
        
        # Формируем event dict
        # Если auto_detect_store включен, не передаем store (будет определен автоматически)
        event_dict = {
            "type": request.event.type,
            "brand": request.event.brand or request.brand,
            "store": None if request.auto_detect_store else request.event.store,
            "auto_detect_store": request.auto_detect_store,  # Передаем флаг автопределения
            **(request.event.metadata or {})
        }
        
        # Определяем список клиентов
        client_ids = []
        segment_client_ids = None
        
        if request.client_ids:
            # Используем переданный список
            for client_id_str in request.client_ids:
                try:
                    client_ids.append(UUID(client_id_str))
                except ValueError:
                    logger.warning(f"Invalid client_id: {client_id_str}")
        
        # Преобразуем search_criteria в dict для передачи в сервис
        search_criteria_dict = None
        if request.search_criteria:
            search_criteria_dict = request.search_criteria.dict(exclude_none=True)
        
        # Валидация входных параметров сегментации
        # Требуем segment_name или segment_id для массовой генерации
        seg_name = None
        seg_id = None
        if search_criteria_dict:
            seg_name = search_criteria_dict.get("segment_name")
            seg_id = search_criteria_dict.get("segment_id")
        
        if not (seg_name or seg_id):
            raise HTTPException(status_code=400, detail="Не указан сегмент. Выберите сегмент перед генерацией.")
        
        # Разрешаем одновременную передачу segment_name и segment_id, приоритет — точное совпадение по ID
        # Загружаем пользователи выбранного сегмента отдельно, чтобы гарантировать ограничение области
        try:
            from app.models.customer_segment import CustomerSegment
            from app.models.user_segment import UserSegment
            from app.models.user import User as UserModel
            from app.api.customer_segmentation import _build_select_for_rules
            seg_uuid = None
            seg_obj = None
            if seg_id:
                try:
                    seg_uuid = UUID(seg_id)
                except Exception:
                    raise HTTPException(status_code=400, detail="Некорректный формат segment_id (UUID).")
                seg_row = await db.execute(
                    select(CustomerSegment).where(
                        CustomerSegment.id == seg_uuid,
                        CustomerSegment.is_active == True,
                    )
                )
                seg_obj = seg_row.scalar_one_or_none()
                if not seg_obj:
                    raise HTTPException(status_code=404, detail=f"Сегмент '{seg_id}' не найден или не активен.")
            if not seg_uuid and seg_name:
                seg_row = await db.execute(
                    select(CustomerSegment).where(
                        CustomerSegment.name == seg_name,
                        CustomerSegment.is_active == True
                    )
                )
                seg_obj = seg_row.scalar_one_or_none()
                if not seg_obj:
                    raise HTTPException(status_code=404, detail=f"Сегмент '{seg_name}' не найден или не активен.")
                seg_uuid = seg_obj.id
            
            # Получаем пользователей сегмента c учётом is_customer
            seg_users_stmt = (
                select(UserSegment.user_id)
                .join(UserModel, UserModel.id == UserSegment.user_id)
                .where(
                    UserSegment.segment_id == seg_uuid,
                    UserModel.is_customer == True
                )
                .limit(request.limit or 1000)
            )
            seg_users_result = await db.execute(seg_users_stmt)
            segment_client_ids = [row[0] for row in seg_users_result.all()]
            if not segment_client_ids and seg_obj is not None:
                rules = seg_obj.rules if isinstance(seg_obj.rules, dict) else {}
                stmt, _ = _build_select_for_rules(rules or {})
                subq = stmt.subquery()
                seg_users_by_rules_stmt = (
                    select(UserModel.id)
                    .where(
                        UserModel.id.in_(select(subq.c.id)),
                        UserModel.is_customer == True,
                    )
                    .limit(request.limit or 1000)
                )
                seg_users_by_rules_result = await db.execute(seg_users_by_rules_stmt)
                segment_client_ids = list(seg_users_by_rules_result.scalars().all())
            logger.info(f"Segment '{seg_name or seg_id}': loaded {len(segment_client_ids)} users (pre-limit).")
        except HTTPException:
            raise
        except Exception as seg_err:
            logger.exception(f"Ошибка при загрузке пользователей сегмента: {seg_err}")
            raise HTTPException(status_code=500, detail="Не удалось прочитать пользователей сегмента.")
        
        use_selected_segment_as_audience = (
            request.event.type == "brand_arrival"
            and segment_client_ids is not None
            and len(segment_client_ids) > 0
        )

        if use_selected_segment_as_audience:
            client_ids = [UUID(str(cid)) for cid in segment_client_ids]
            logger.info(
                "Using selected segment as brand_arrival audience: %s clients. "
                "Brand is used as event context, not as an extra purchase-history filter.",
                len(client_ids),
            )
        elif request.brand:
            # Ищем клиентов по бренду
            client_ids = await service.find_clients_by_brand(
                request.brand,
                limit=request.limit or 100,
                search_criteria=search_criteria_dict
            )
        
        elif request.event.type:
            # Ищем клиентов для события
            client_ids = await service.find_clients_for_event(
                request.event.type,
                event_data=event_dict,
                limit=request.limit or 100,
                search_criteria=search_criteria_dict
            )
        else:
            # Без event.type — ошибка запроса
            raise HTTPException(status_code=400, detail="Не указан тип события (event.type).")
        
        # Пересекаем со списком клиентов выбранного сегмента
        if segment_client_ids is not None and not use_selected_segment_as_audience:
            seg_set = {UUID(str(cid)) for cid in segment_client_ids}
            if client_ids:
                client_ids = [cid for cid in client_ids if cid in seg_set]
            else:
                client_ids = list(seg_set)
        
        # Жёстко ограничиваем итоговую выборку лимитом
        lim = request.limit or 100
        client_ids = client_ids[:lim]
        
        # Создаём запись в истории генераций (пока total=0, обновим после получения client_ids)
        rec_id = await history.create(
            event_type=request.event.type,
            segment=seg_name or seg_id,
            total=len(client_ids),
            params={
                "brand": request.brand or request.event.brand,
                "limit": lim if 'lim' in locals() else (request.limit or 100),
                "auto_detect_store": request.auto_detect_store,
                "criteria": search_criteria_dict,
            }
        )
        
        if not client_ids:
            # Получаем более детальную информацию о причине
            debug_info = {
                "event_type": request.event.type,
                "has_brand": bool(request.brand or request.event.brand),
                "brand": request.brand or request.event.brand,
                "has_client_ids": bool(request.client_ids),
                "client_ids_count": len(request.client_ids) if request.client_ids else 0,
                "limit": lim,
                "segment": seg_name or seg_id,
                "segment_users_count": len(segment_client_ids or [])
            }
            
            logger.warning(f"No clients found for criteria: {debug_info}")
            
            # Проверяем, есть ли вообще клиенты в базе
            from app.models.user import User
            total_customers_result = await db.execute(
                select(func.count(User.id)).where(User.is_customer == True)
            )
            total_customers = total_customers_result.scalar() or 0
            
            error_message = "Клиенты не найдены для указанных критериев"
            if request.event.type == "brand_arrival" and (request.brand or request.event.brand):
                error_message = f"Клиенты с брендом '{request.brand or request.event.brand}' не найдены в истории покупок"
            elif total_customers == 0:
                error_message = "В базе данных нет клиентов. Выполните синхронизацию с 1С."
            elif request.event.type == "no_purchase_180":
                error_message = "Клиенты без покупок более 180 дней не найдены"
            elif request.event.type == "bonus_balance":
                error_message = "Клиенты с балансом бонусов не найдены"
            elif seg_name or seg_id:
                seg_label = seg_name or seg_id
                error_message = f"В сегменте «{seg_label}» не найдено клиентов, соответствующих выбранному событию и критериям"
            
            response_data = {
                "status": "success",
                "messages": [],
                "count": 0,
                "message": error_message,
                "debug_info": debug_info,
                "total_customers_in_db": total_customers,
            }
            saved_file = await _write_generation_result_file(rec_id, request.event.type, response_data)
            await history.complete(rec_id, saved_file=saved_file, result=response_data)
            return {
                "status": "success",
                "messages": [],
                "count": 0,
                "message": error_message,
                "debug_info": debug_info,
                "total_customers_in_db": total_customers
            }
        
        # Генерируем сообщения
        messages = []
        errors = []
        total_clients = len(client_ids)
        
        logger.info(f"Starting batch generation for {total_clients} clients")
        
        for idx, client_id in enumerate(client_ids, 1):
            try:
                # Логируем прогресс каждые 10 клиентов или для первых 5
                if idx <= 5 or idx % 10 == 0 or idx == total_clients:
                    logger.info(f"Processing client {idx}/{total_clients}: {client_id}")
                
                # Получаем данные клиента
                client_data = await service.get_client_data(client_id)
                
                if not client_data:
                    logger.warning(f"Client data not found for {client_id}")
                    continue
                
                # Генерируем сообщение
                message = await agent.generate_message(
                    client_id=client_id,
                    event=event_dict,
                    client_data=client_data,
                    max_length=request.max_length
                )
                
                messages.append(message)
                # обновляем прогресс
                await history.update_progress(rec_id, processed=idx, success=len(messages), errors=len(errors))
                
                # Логируем успех для первых сообщений
                if idx <= 3:
                    logger.info(f"Successfully generated message for client {idx}: {client_id}")
            
            except Exception as e:
                logger.warning(f"Failed to generate message for client {client_id} ({idx}/{total_clients}): {e}")
                errors.append({
                    "client_id": str(client_id),
                    "error": str(e)
                })
                continue
        
        logger.info(f"Batch generation completed: {len(messages)} messages, {len(errors)} errors")
        
        # Убеждаемся, что все данные сериализуемы
        try:
            # Преобразуем все сообщения в словари, если они еще не словари
            serialized_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    serialized_messages.append(msg)
                else:
                    # Если это объект, преобразуем в dict
                    serialized_messages.append({
                        "client_id": str(getattr(msg, "client_id", "")),
                        "phone": getattr(msg, "phone", None),
                        "name": getattr(msg, "name", None),
                        "gender": getattr(msg, "gender", None),
                        "segment": getattr(msg, "segment", ""),
                        "reason": getattr(msg, "reason", ""),
                        "message": getattr(msg, "message", ""),
                        "cta": getattr(msg, "cta", ""),
                        "brand": getattr(msg, "brand", None),
                        "store": getattr(msg, "store", None),
                    })
            
            response_data = {
                "status": "success",
                "messages": serialized_messages,
                "count": len(serialized_messages),
                "errors": errors if errors else None
            }

            try:
                await _persist_generated_messages(
                    db,
                    messages=serialized_messages,
                    message_kind="broadcast",
                    generation_id=rec_id,
                    default_event_type=request.event.type,
                    default_event_brand=request.event.brand or request.brand,
                    default_event_store=request.event.store,
                )
                for m in serialized_messages[:20]:
                    client_id_raw = m.get("client_id")
                    if client_id_raw:
                        try:
                            _invalidate_customer_messages_cache(UUID(str(client_id_raw)))
                        except Exception:
                            pass
            except Exception as persist_err:
                logger.exception(f"Не удалось сохранить сообщения в историю для generation_id={rec_id}: {persist_err}")
                await db.rollback()
                raise HTTPException(status_code=500, detail="Не удалось сохранить сообщения в историю пользователя.")
            
            # Проверяем, что можем сериализовать ответ
            import json
            try:
                json_str = json.dumps(response_data, default=str, ensure_ascii=False)
                logger.debug(f"Response JSON length: {len(json_str)}")
            except Exception as json_error:
                logger.error(f"JSON serialization test failed: {json_error}")
                raise
            
            logger.info(f"Response prepared: {len(serialized_messages)} messages, {len(errors)} errors")
            
            # Проверяем размер ответа
            import sys
            response_size = sys.getsizeof(response_data)
            logger.info(f"Response data size: {response_size} bytes")
            
            # Финальная проверка сериализации перед возвратом
            try:
                # Пытаемся сериализовать в JSON строку для проверки
                json_str = json.dumps(response_data, default=str, ensure_ascii=False)
                logger.info(f"Response JSON serialization successful, length: {len(json_str)} bytes")
            except Exception as json_check_error:
                logger.exception(f"Final JSON check failed: {json_check_error}")
                logger.error(f"Response data structure: {type(response_data)}")
                logger.error(f"Messages type: {type(serialized_messages)}")
                if serialized_messages:
                    logger.error(f"First message type: {type(serialized_messages[0])}, keys: {serialized_messages[0].keys() if isinstance(serialized_messages[0], dict) else 'not a dict'}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Response serialization failed: {str(json_check_error)}"
                )
            
            # Возвращаем ответ напрямую как dict - FastAPI автоматически сериализует в JSON
            # Это более надежно, чем JSONResponse, так как избегает проблем с кодировкой
            logger.info(f"Returning response as dict, messages count: {len(serialized_messages)}, errors: {len(errors) if errors else 0}")
            
            # Финальная проверка: убеждаемся, что все значения сериализуемы
            try:
                # Проверяем каждое сообщение на наличие несериализуемых объектов
                for i, msg in enumerate(serialized_messages):
                    for key, value in msg.items():
                        if value is not None:
                            # Пытаемся сериализовать каждое значение
                            try:
                                json.dumps(value, default=str, ensure_ascii=False)
                            except (TypeError, ValueError) as ser_error:
                                logger.error(f"Non-serializable value in message {i}, key '{key}': {type(value)} = {value}, error: {ser_error}")
                                # Заменяем на строковое представление
                                serialized_messages[i][key] = str(value)
                
                # Финальная проверка всего ответа
                test_json = json.dumps(response_data, default=str, ensure_ascii=False)
                logger.info(f"Final serialization test passed, JSON length: {len(test_json)} bytes")
            except Exception as final_check_error:
                logger.exception(f"Error in final serialization check: {final_check_error}")
                # Продолжаем, так как FastAPI может справиться
            
            logger.info("About to return response_data...")
            
            # Сохраняем результаты в файл на сервере
            # Пишем асинхронно и с ретраями; ошибки записи не влияют на HTTP-ответ
            # Формируем директорию и имя файла
            project_root = Path(__file__).parent.parent.parent
            save_dir = project_root / "backend" / "generated_messages"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            event_type = request.event.type or "unknown"
            safe_event_type = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in event_type)
            filename = f"messages_{safe_event_type}_{timestamp}.json"
            filepath = save_dir / filename
            response_data["saved_file"] = str(filepath)
            response_data["saved_file_name"] = filename

            async def _writer():
                res = await _safe_write_json_with_retries(filepath, response_data, attempts=5, delay=0.4)
                if not res["success"]:
                    logger.error(f"Ошибка записи JSON файла {filepath}: {res['error']}")
                    try:
                        await history.fail(rec_id, f"Ошибка записи файла: {res['error']}")
                    except Exception:
                        logger.exception("Не удалось обновить статус истории при ошибке записи файла")
                else:
                    logger.info(f"✅ Сохранено {len(serialized_messages)} сообщений в файл: {filepath}")
                    try:
                        await history.complete(rec_id, saved_file=str(filepath), result={
                            "status": "success",
                            "count": len(serialized_messages),
                            "errors": len(errors) if errors else 0
                        })
                    except Exception:
                        logger.exception("Не удалось зафиксировать завершение генерации в истории")

            try:
                asyncio.create_task(_writer())
            except Exception as save_error:
                logger.exception(f"Не удалось запланировать запись файла: {save_error}")
            
            # Используем JSONResponse с явной сериализацией для максимальной надежности
            try:
                # Сериализуем в JSON строку
                json_str = json.dumps(response_data, default=str, ensure_ascii=False)
                logger.info(f"Serialized to JSON string, length: {len(json_str)} bytes")
                
                # Создаем JSONResponse с сериализованными данными
                # Используем content напрямую (dict), FastAPI сам сериализует
                logger.info("Creating JSONResponse...")
                response = JSONResponse(
                    content=response_data,  # Передаем dict, JSONResponse сам сериализует
                    status_code=200
                )
                logger.info("JSONResponse created successfully, returning...")
                return response
            except Exception as json_response_error:
                logger.exception(f"Error creating JSONResponse: {json_response_error}")
                # Fallback: возвращаем как dict
                logger.warning("Falling back to dict return")
                return response_data
            
        except Exception as serialization_error:
            logger.exception(f"Error serializing response: {serialization_error}")
            logger.error(f"Messages type: {type(messages)}, Errors type: {type(errors)}")
            if messages:
                logger.error(f"First message type: {type(messages[0])}, content: {messages[0]}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error serializing response: {str(serialization_error)}"
            )
    
    except HTTPException as http_ex:
        logger.warning(f"HTTPException in batch generation: {http_ex.status_code} - {http_ex.detail}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in batch generation: {e}")
        # Пытаемся пометить запись как упавшую
        try:
            history = get_generation_history()
            # rec_id мог быть ещё не создан в крайних случаях
            if 'rec_id' in locals():
                await history.fail(rec_id, str(e))
        except Exception:
            logger.exception("Не удалось записать ошибку в историю генераций")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error args: {e.args}")
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_traceback}")
        
        # Возвращаем частичные результаты, если они есть
        if 'messages' in locals() and messages:
            logger.warning(f"Returning partial results: {len(messages)} messages generated before error")
            try:
                # Сериализуем частичные результаты
                serialized_messages = []
                for msg in messages:
                    if isinstance(msg, dict):
                        serialized_messages.append(msg)
                    else:
                        serialized_messages.append({
                            "client_id": str(getattr(msg, "client_id", "")),
                            "phone": getattr(msg, "phone", None),
                            "name": getattr(msg, "name", None),
                            "gender": getattr(msg, "gender", None),
                            "segment": getattr(msg, "segment", ""),
                            "reason": getattr(msg, "reason", ""),
                            "message": getattr(msg, "message", ""),
                            "cta": getattr(msg, "cta", ""),
                            "brand": getattr(msg, "brand", None),
                            "store": getattr(msg, "store", None),
                        })
                
                return {
                    "status": "partial_success",
                    "messages": serialized_messages,
                    "count": len(serialized_messages),
                    "error": f"Generation interrupted: {str(e)}",
                    "errors": errors if 'errors' in locals() else []
                }
            except Exception as partial_error:
                logger.error(f"Error returning partial results: {partial_error}")
        
        raise HTTPException(status_code=500, detail=f"Error in batch generation: {str(e)}")


@router.get("/generations/{rec_id}/events")
async def stream_generation_events(rec_id: str, request: Request):
    """
    Server-Sent Events поток статуса генерации.
    Отправляет полную запись GenerationHistory при каждом изменении.
    """
    history = get_generation_history()

    async def event_generator():
        last_snapshot: Optional[str] = None
        try:
            while True:
                if await request.is_disconnected():
                    logger.info(f"SSE client disconnected for generation {rec_id}")
                    break

                rec = await history.get(rec_id)
                if rec is None:
                    payload = json.dumps({"event": "not_found", "id": rec_id}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    break

                snapshot = json.dumps(rec, ensure_ascii=False)
                if snapshot != last_snapshot:
                    last_snapshot = snapshot
                    yield f"data: {snapshot}\n\n"

                if rec.get("status") in {"completed", "failed"}:
                    break

                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for generation {rec_id}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/batch-generate-async", response_model=BatchGenerateAsyncResponse)
async def batch_generate_messages_async(request: BatchGenerateRequest):
    """
    Асинхронный запуск батч-генерации.
    Возвращает идентификатор генерации и URL для SSE-событий.
    """
    history = get_generation_history()
    search_criteria_dict = request.search_criteria.dict(exclude_none=True) if request.search_criteria else None
    seg_name = None
    seg_id = None
    if search_criteria_dict:
        seg_name = search_criteria_dict.get("segment_name")
        seg_id = search_criteria_dict.get("segment_id")
    segment_label = seg_name or seg_id
    params = {
        "brand": request.brand or request.event.brand,
        "limit": request.limit or 100,
        "auto_detect_store": request.auto_detect_store,
        "criteria": search_criteria_dict,
    }
    rec_id = await history.create(
        event_type=request.event.type,
        segment=segment_label,
        total=0,
        params=params,
    )

    try:
        asyncio.create_task(_run_batch_generate_task(rec_id, request.dict()))
    except Exception as e:
        logger.exception(f"Не удалось запустить фоновую задачу генерации: {e}")
        await history.fail(rec_id, f"Не удалось запустить задачу: {e}")
        raise HTTPException(status_code=500, detail="Не удалось запустить фоновую генерацию сообщений")

    return BatchGenerateAsyncResponse(
        status="started",
        generation_id=rec_id,
        events_url=f"/api/communication/generations/{rec_id}/events",
    )


@router.get("/generations/{gen_id}/result")
async def get_generation_result(gen_id: str):
    """
    Возвращает JSON-результат генерации по её идентификатору.
    Читает файл из saved_file в истории генераций.
    """
    history = get_generation_history()
    rec = await history.get(gen_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    saved_file = rec.get("saved_file")
    if not saved_file:
        if rec.get("status") == "completed" and int(rec.get("total") or 0) == 0:
            return JSONResponse(status_code=200, content={
                "status": "success",
                "messages": [],
                "count": 0,
                "message": rec.get("error_message") or "Для выбранных условий не найдено клиентов",
            })
        raise HTTPException(status_code=404, detail="Файл результата не зарегистрирован")
    try:
        p = Path(saved_file)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Файл результата не найден")
        # Читаем как есть и возвращаем содержимое
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        # Минимальная валидация структуры
        if not isinstance(data, dict) or "messages" not in data:
            data = {"status": "success", "messages": data, "count": len(data) if isinstance(data, list) else 0}
        return JSONResponse(status_code=200, content=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Не удалось прочитать результат генерации {gen_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка чтения файла результата")


class UpdateGenerationMessageRequest(BaseModel):
    message: str
    cta: Optional[str] = None


@router.put("/generations/{gen_id}/messages/{client_id}")
async def update_generation_message(
    gen_id: str,
    client_id: str,
    request: UpdateGenerationMessageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Обновляет текст сообщения для конкретного клиента в результате генерации.
    Обновляет JSON-файл и запись в БД.
    """
    history = get_generation_history()
    rec = await history.get(gen_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Generation not found")
    
    saved_file = rec.get("saved_file")
    if not saved_file:
        raise HTTPException(status_code=404, detail="Result file not registered")
        
    p = Path(saved_file)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
        
    try:
        # 1. Читаем файл
        read_res = await _safe_read_json_with_retries(p)
        if not read_res["success"]:
            raise HTTPException(status_code=500, detail=f"Error reading file: {read_res['error']}")
            
        data = read_res["data"]
        messages = []
        is_dict = isinstance(data, dict)
        if is_dict and "messages" in data:
            messages = data["messages"]
        elif isinstance(data, list):
            messages = data
        else:
             raise HTTPException(status_code=500, detail="Invalid file format")
             
        # 2. Ищем и обновляем сообщение
        updated = False
        target_msg = None
        for msg in messages:
            if str(msg.get("client_id")) == client_id:
                msg["message"] = request.message
                if request.cta is not None:
                    msg["cta"] = request.cta
                target_msg = msg
                updated = True
                break
        
        if not updated:
            raise HTTPException(status_code=404, detail="Client message not found in generation result")
            
        # 3. Сохраняем файл
        if is_dict:
            data["messages"] = messages
        else:
            data = messages
            
        write_res = await _safe_write_json_with_retries(p, data)
        if not write_res["success"]:
             raise HTTPException(status_code=500, detail=f"Error writing file: {write_res['error']}")
             
        # 4. Обновляем БД (CustomerMessage)
        try:
            client_uuid = UUID(client_id)
            msg_id = _deterministic_batch_message_id(gen_id, client_uuid)
            
            # Обновляем
            values = {"message": request.message}
            if request.cta is not None:
                values["cta"] = request.cta
                
            stmt = (
                update(CustomerMessage)
                .where(CustomerMessage.id == msg_id)
                .values(**values)
            )
            await db.execute(stmt)
            await db.commit()
            
            _invalidate_customer_messages_cache(client_uuid)
        except Exception as e:
            logger.warning(f"Failed to update CustomerMessage in DB: {e}")
            # Не фейлим запрос, если файл обновился
            
        return {"status": "success", "message": "Message updated"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class GenerationBackfillResponse(BaseModel):
    status: str
    processed: int


@router.post("/generations/{gen_id}/backfill-messages", response_model=GenerationBackfillResponse)
async def backfill_generation_messages(
    gen_id: str,
    db: AsyncSession = Depends(get_db),
):
    history = get_generation_history()
    rec = await history.get(gen_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    saved_file = rec.get("saved_file")
    if not saved_file:
        raise HTTPException(status_code=404, detail="Файл результата не зарегистрирован")
    try:
        p = Path(saved_file)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Файл результата не найден")
        import json
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "messages" in raw:
            messages = raw.get("messages") or []
        else:
            messages = raw or []
        if not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Некорректная структура файла результата")
        await _persist_generated_messages(
            db,
            messages=messages,
            message_kind="broadcast",
            generation_id=gen_id,
            default_event_type=rec.get("event_type"),
            default_event_brand=None,
            default_event_store=None,
        )
        for m in messages[:50]:
            client_id_raw = m.get("client_id") if isinstance(m, dict) else None
            if client_id_raw:
                try:
                    _invalidate_customer_messages_cache(UUID(str(client_id_raw)))
                except Exception:
                    pass
        return GenerationBackfillResponse(status="ok", processed=len(messages))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Не удалось выполнить бэкап сообщений генерации {gen_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка бэкапа сообщений генерации")


class GenerationsDeleteFilesRequest(BaseModel):
    ids: List[str]


@router.post("/generations/delete-files")
async def delete_generation_files(
    req: GenerationsDeleteFilesRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Удаляет генерации из истории и связанные JSON-файлы результатов по списку generation_id.
    Правила безопасности:
    - Удаляем только файлы из директории backend/generated_messages
    - Путь берём строго из saved_file записи истории
    - После успешного удаления удаляем запись(и) из history.jsonl
    """
    history = get_generation_history()
    project_root = Path(__file__).parent.parent.parent
    base_dir = project_root / "backend" / "generated_messages"
    deleted: List[str] = []
    failed: Dict[str, str] = {}

    for gen_id in req.ids:
        try:
            rec = await history.get(gen_id)
            if not rec:
                failed[gen_id] = "Запись не найдена"
                continue
            saved_file = rec.get("saved_file")
            p = Path(saved_file) if saved_file else None
            tmp_path: Optional[Path] = None
            if p:
                try:
                    p_resolved = p.resolve()
                    if base_dir not in p_resolved.parents and p_resolved != base_dir:
                        failed[gen_id] = "Недопустимый путь файла"
                        continue
                except Exception:
                    failed[gen_id] = "Недействительный путь файла"
                    continue

                if p.exists():
                    tmp_path = p.with_name(p.name + ".deleting")
                    try:
                        await asyncio.to_thread(os.replace, p, tmp_path)
                    except Exception as e:
                        failed[gen_id] = f"Не удалось подготовить файл к удалению: {e}"
                        continue

            deleted_user_ids: List[UUID] = []
            try:
                async with db.begin():
                    deleted_user_ids = await _delete_messages_by_generation_ids(db, [gen_id])
                    if tmp_path and tmp_path.exists():
                        await asyncio.to_thread(tmp_path.unlink)
            except Exception as e:
                if tmp_path and tmp_path.exists() and p and (not p.exists()):
                    try:
                        await asyncio.to_thread(os.replace, tmp_path, p)
                    except Exception:
                        pass
                failed[gen_id] = f"Не удалось удалить из БД/файловой системы: {e}"
                continue

            try:
                await history.delete_records([gen_id])
            except Exception as e:
                logger.exception(f"Не удалось удалить запись истории генерации {gen_id}: {e}")
                failed[gen_id] = "Сообщения удалены, но не удалось обновить историю"
                continue

            for uid in deleted_user_ids[:500]:
                try:
                    _invalidate_customer_messages_cache(uid)
                except Exception:
                    pass

            deleted.append(gen_id)
        except Exception as e:
            failed[gen_id] = str(e)

    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_count": len(deleted),
        "failed_count": len(failed),
    }


@router.get("/clients/by-brand")
async def get_clients_by_brand(
    brand: str = Query(..., description="Название бренда"),
    limit: int = Query(100, ge=1, le=1000, description="Максимальное количество клиентов"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка клиентов, у которых в истории есть указанный бренд
    """
    try:
        service = CommunicationService(db)
        client_ids = await service.find_clients_by_brand(brand, limit)
        
        return {
            "status": "success",
            "brand": brand,
            "client_ids": [str(cid) for cid in client_ids],
            "count": len(client_ids)
        }
    
    except Exception as e:
        logger.exception(f"Error getting clients by brand: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/clients/{client_id}/data")
async def get_client_data(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение данных клиента для генерации сообщения
    """
    try:
        try:
            client_uuid = UUID(client_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid client_id format: {client_id}")
        
        service = CommunicationService(db)
        client_data = await service.get_client_data(client_uuid)
        
        if not client_data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        return {
            "status": "success",
            "client": client_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting client data: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/brands/available")
async def get_available_brands(
    limit: int = Query(100, ge=1, le=1000, description="Максимальное количество брендов"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка доступных брендов из истории покупок
    """
    try:
        from sqlalchemy import func, distinct
        from app.models.purchase_history import PurchaseHistory
        
        # Получаем уникальные бренды с количеством клиентов
        result = await db.execute(
            select(
                PurchaseHistory.brand,
                func.count(distinct(PurchaseHistory.user_id)).label('client_count')
            )
            .where(PurchaseHistory.brand.isnot(None))
            .group_by(PurchaseHistory.brand)
            .order_by(func.count(distinct(PurchaseHistory.user_id)).desc())
            .limit(limit)
        )
        
        brands = [
            {
                "brand": row[0],
                "client_count": row[1]
            }
            for row in result.all()
            if row[0]  # Фильтруем пустые значения
        ]
        
        return {
            "status": "success",
            "brands": brands,
            "count": len(brands)
        }
    
    except Exception as e:
        logger.exception(f"Error getting available brands: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ===== История генераций =====

class GenerationsExportRequest(BaseModel):
    ids: List[str]
    columns: Optional[List[str]] = None  # если None — экспортируем стандартный набор


@router.get("/generations")
async def list_generations(
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("started_at"),
    desc: bool = Query(True),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    history = get_generation_history()
    total, items = await history.list(
        status=status,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sort_by=sort_by,
        desc=desc,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": items}


@router.get("/generations/{gen_id}")
async def get_generation(gen_id: str):
    history = get_generation_history()
    rec = await history.get(gen_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return rec


@router.post("/generations/export")
async def export_generations(req: GenerationsExportRequest):
    """Экспорт выбранных записей в .xlsx (openpyxl)."""
    history = get_generation_history()
    records = []
    for rid in req.ids:
        rec = await history.get(rid)
        if rec:
            records.append(rec)
    if not records:
        raise HTTPException(status_code=400, detail="Нет записей для экспорта")
    
    # Выбор столбцов
    default_cols = ["id", "status", "event_type", "segment", "started_at", "completed_at", "total", "processed", "success", "errors", "saved_file"]
    cols = req.columns or default_cols
    
    # Генерация XLSX в памяти
    try:
        from openpyxl import Workbook
        from io import BytesIO
        wb = Workbook()
        ws = wb.active
        ws.title = "Generations"
        # Заголовки
        ws.append(cols)
        # Строки
        for r in records:
            row = [r.get(c) for c in cols]
            ws.append(row)
        # Стили для дат и чисел можно доработать; базовая совместимость сохранена
        stream = BytesIO()
        wb.save(stream)
        data = stream.getvalue()
        filename = f"generations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.exception(f"Ошибка экспорта в Excel: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {str(e)}")


@router.get("/generations/{gen_id}/messages/export")
async def export_generation_messages(
    gen_id: str,
    db: AsyncSession = Depends(get_db),
    columns: Optional[List[str]] = Query(None),
    fmt: str = Query("xlsx")
):
    stmt = (
        select(CustomerMessage, User)
        .join(User, User.id == CustomerMessage.user_id)
        .where(CustomerMessage.payload["generation_id"].astext == gen_id)
        .order_by(CustomerMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Сообщения не найдены")
    default_cols = [
        "user_id",
        "phone",
        "full_name",
        "gender",
        "loyalty_points",
        "total_purchases",
        "total_spent",
        "last_purchase_date",
        "segment",
        "event_type",
        "event_brand",
        "event_store",
        "message",
        "cta",
        "created_at",
    ]
    cols = columns or default_cols
    if fmt.lower() != "xlsx":
        raise HTTPException(status_code=400, detail="Поддерживается только формат xlsx")
    try:
        from openpyxl import Workbook
        from io import BytesIO
        wb = Workbook()
        ws = wb.active
        ws.title = "Messages"
        ws.append(cols)
        for msg, user in rows:
            total_spent_rub = (user.total_spent or 0) / 100.0
            row_map = {
                "user_id": str(user.id),
                "phone": user.phone,
                "full_name": user.full_name,
                "gender": user.gender if hasattr(user, "gender") else None,
                "loyalty_points": getattr(user, "loyalty_points", None),
                "total_purchases": getattr(user, "total_purchases", None),
                "total_spent": total_spent_rub,
                "last_purchase_date": user.last_purchase_date.isoformat() if getattr(user, "last_purchase_date", None) else None,
                "segment": msg.segment,
                "event_type": msg.event_type,
                "event_brand": msg.event_brand,
                "event_store": msg.event_store,
                "message": msg.message,
                "cta": msg.cta,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            ws.append([row_map.get(c) for c in cols])
        stream = BytesIO()
        wb.save(stream)
        data = stream.getvalue()
        filename = f"messages_{gen_id}.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.exception(f"Ошибка экспорта сообщений генерации {gen_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка экспорта сообщений")


class RecipientsAggregatesResponse(BaseModel):
    generation_id: str
    total_recipients: int
    loyalty_points_sum: int
    r_distribution: Dict[str, int]
    f_distribution: Dict[str, int]
    m_distribution: Dict[str, int]
    sample: List[Dict[str, Any]] = []


@router.get("/generations/{gen_id}/recipients", response_model=RecipientsAggregatesResponse)
async def get_generation_recipients_aggregates(
    gen_id: str,
    limit_sample: int = Query(20, ge=0, le=200),
    db: AsyncSession = Depends(get_db),
):
    history = get_generation_history()
    rec = await history.get(gen_id)
    client_ids: List[UUID] = []
    try:
        res = await db.execute(
            select(CustomerMessage.user_id)
            .where(CustomerMessage.payload["generation_id"].astext == gen_id)
        )
        client_ids = [r[0] for r in res.fetchall() if r and r[0]]
    except Exception:
        client_ids = []
    if not client_ids and rec and rec.get("saved_file"):
        try:
            p = Path(rec.get("saved_file"))
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                msgs = raw.get("messages") if isinstance(raw, dict) else raw
                if isinstance(msgs, list):
                    ids: List[UUID] = []
                    for m in msgs:
                        cid = None
                        if isinstance(m, dict):
                            cid = m.get("client_id")
                        if cid:
                            try:
                                ids.append(UUID(str(cid)))
                            except Exception:
                                pass
                    client_ids = ids
        except Exception:
            pass
    if not client_ids:
        return RecipientsAggregatesResponse(
            generation_id=gen_id,
            total_recipients=0,
            loyalty_points_sum=0,
            r_distribution={str(i): 0 for i in range(1, 6)},
            f_distribution={str(i): 0 for i in range(1, 6)},
            m_distribution={str(i): 0 for i in range(1, 6)},
            sample=[],
        )
    q = await db.execute(select(User).where(User.id.in_(client_ids)))
    users = q.scalars().all()
    total = len(users)
    loyalty_sum = 0
    r = defaultdict(int)
    f = defaultdict(int)
    m = defaultdict(int)
    sample: List[Dict[str, Any]] = []
    for u in users:
        lp = getattr(u, "loyalty_points", 0) or 0
        loyalty_sum += lp
        rfm = getattr(u, "rfm_score", None) or {}
        rv = int(rfm.get("r_score", 0) or 0)
        fv = int(rfm.get("f_score", 0) or 0)
        mv = int(rfm.get("m_score", 0) or 0)
        if 1 <= rv <= 5:
            r[str(rv)] += 1
        if 1 <= fv <= 5:
            f[str(fv)] += 1
        if 1 <= mv <= 5:
            m[str(mv)] += 1
    if limit_sample > 0:
        for u in users[:limit_sample]:
            sample.append(
                {
                    "id": str(u.id),
                    "phone": u.phone,
                    "full_name": u.full_name,
                    "loyalty_points": getattr(u, "loyalty_points", None),
                    "rfm_score": getattr(u, "rfm_score", None),
                }
            )
    def ensure_all(d: Dict[str, int]) -> Dict[str, int]:
        out = {str(i): 0 for i in range(1, 6)}
        out.update({str(k): int(v) for k, v in d.items()})
        return out
    return RecipientsAggregatesResponse(
        generation_id=gen_id,
        total_recipients=total,
        loyalty_points_sum=loyalty_sum,
        r_distribution=ensure_all(r),
        f_distribution=ensure_all(f),
        m_distribution=ensure_all(m),
        sample=sample,
    )


class SendGenerationSmsRequest(BaseModel):
    date_send: Optional[datetime] = None
    periodicity: Optional[str] = None


async def _send_sms_task(gen_id: str, messages: List[Dict[str, Any]], date_send: Optional[datetime]):
    from app.database.connection import AsyncSessionLocal
    from sqlalchemy import update
    
    sms_service = get_sms_service()
    if not sms_service:
        return

    unixtime = None
    if date_send:
        # Если время отправки в прошлом, отправляем сразу (unixtime=None)
        # SMS Aero возвращает ошибку "Date is too small" если время меньше текущего
        now_utc = datetime.now(timezone.utc)
        if date_send.tzinfo is None:
            date_send = date_send.replace(tzinfo=timezone.utc)
            
        if date_send > now_utc:
            unixtime = int(date_send.timestamp())
            
    # Если отложенная отправка - ставим дату отправки как запланированную, иначе текущую
    actual_sent_at = date_send if unixtime else datetime.now(timezone.utc)
    
    sent_count = 0
    errors_count = 0
    
    logger.info(f"Starting SMS sending for generation {gen_id}, count: {len(messages)}")
    
    async with AsyncSessionLocal() as db:
        for msg in messages:
            try:
                phone = msg.get("phone")
                text = msg.get("message")
                client_id = msg.get("client_id")
                
                if not phone or not text:
                    continue
                    
                clean_phone = "".join(c for c in str(phone) if c.isdigit())
                if len(clean_phone) == 11 and clean_phone.startswith("8"):
                    clean_phone = "7" + clean_phone[1:]
                elif len(clean_phone) == 10:
                    clean_phone = "7" + clean_phone
                
                response = await sms_service.send_sms(clean_phone, text, sign="GLAME", date_send=unixtime)
                
                # SMS Aero returns data structure:
                # { "success": true, "data": { "id": 12345, ... }, "message": null }
                sms_id = None
                if response.get("success") and response.get("data"):
                    data = response.get("data")
                    if isinstance(data, dict):
                        sms_id = data.get("id")
                
                sent_count += 1
                
                if client_id:
                    try:
                        # Обновляем статус в БД
                        msg_id = _deterministic_batch_message_id(gen_id, UUID(str(client_id)))
                        
                        # Сохраняем sms_id в payload, если есть
                        update_values = {"status": 'sent', "sent_at": actual_sent_at}
                        
                        if sms_id:
                            # Нужно аккуратно обновить payload, не затирая остальное
                            # Но в SQL update это сложно сделать атомарно для jsonb без чтения
                            # Попробуем jsonb_set или просто добавим поле, если поддерживается
                            # Для простоты пока просто статус
                            pass

                        stmt = (
                            update(CustomerMessage)
                            .where(CustomerMessage.id == msg_id)
                            .values(**update_values)
                        )
                        # Если есть sms_id, добавим его в payload через jsonb_set или аналог
                        # Но так как мы используем sqlalchemy async, проще сделать два запроса или один умный
                        # Пока оставим как есть, главное статус
                        
                        await db.execute(stmt)
                        
                        # Если есть sms_id, попробуем обновить payload отдельно или сразу
                        if sms_id:
                            # update payload = jsonb_set(payload, '{sms_id}', '12345')
                            from sqlalchemy import text as sql_text
                            await db.execute(
                                sql_text("UPDATE customer_messages SET payload = jsonb_set(payload, '{sms_id}', :sms_id) WHERE id = :msg_id"),
                                {"sms_id": str(sms_id), "msg_id": msg_id}
                            )

                        _invalidate_customer_messages_cache(UUID(str(client_id)))
                    except Exception as db_err:
                        logger.error(f"Failed to update status for {client_id}: {db_err}")

            except Exception as e:
                logger.error(f"Failed to send SMS to {phone}: {e}")
                errors_count += 1
        
        await db.commit()
            
    logger.info(f"Finished SMS sending for generation {gen_id}. Sent: {sent_count}, Errors: {errors_count}")


@router.post("/generations/{gen_id}/send")
async def send_generation_sms(
    gen_id: str,
    request: SendGenerationSmsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправить SMS по результатам генерации.
    """
    history = get_generation_history()
    rec = await history.get(gen_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    
    sms_service = get_sms_service()
    if not sms_service:
        raise HTTPException(status_code=503, detail="Сервис SMS Aero не настроен (проверьте переменные окружения)")
        
    saved_file = rec.get("saved_file")
    if not saved_file:
        raise HTTPException(status_code=404, detail="Файл результата не найден")
        
    p = Path(saved_file)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Файл результата не найден")
        
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        messages = raw.get("messages") if isinstance(raw, dict) else raw
        if not isinstance(messages, list):
            messages = []
            
        asyncio.create_task(_send_sms_task(gen_id, messages, request.date_send))
        
        return {"status": "started", "message": "Рассылка запущена в фоновом режиме"}
        
    except Exception as e:
        logger.exception(f"Ошибка запуска рассылки: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка запуска рассылки: {e}")
