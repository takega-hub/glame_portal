"""
API endpoints для генерации персональных сообщений клиентам
"""
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from app.database.connection import get_db
from app.agents.communication_agent import CommunicationAgent
from app.services.communication_service import CommunicationService
from app.models.user import User
from app.models.customer_message import CustomerMessage

logger = logging.getLogger(__name__)

router = APIRouter()


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
    search_criteria: Optional[SearchCriteria] = None  # Дополнительные критерии поиска
    auto_detect_store: Optional[bool] = False  # Автоматическое определение бутика из истории покупок или города


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
            payload=result,
            status="new",
        )
        db.add(msg)
        await db.commit()
        
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
):
    """Список сгенерированных сообщений для покупателя (история общения)."""
    result = await db.execute(
        select(CustomerMessage)
        .where(CustomerMessage.user_id == customer_id)
        .order_by(CustomerMessage.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()
    count_result = await db.execute(
        select(func.count()).select_from(CustomerMessage).where(CustomerMessage.user_id == customer_id)
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
            status=m.status,
            sent_at=m.sent_at,
            created_at=m.created_at,
        )
        for m in messages
    ]
    return CustomerMessagesListResponse(items=items, total=total)


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
    db.delete(msg)
    await db.commit()
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
        
        if request.brand:
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
        
        if not client_ids:
            # Получаем более детальную информацию о причине
            debug_info = {
                "event_type": request.event.type,
                "has_brand": bool(request.brand or request.event.brand),
                "brand": request.brand or request.event.brand,
                "has_client_ids": bool(request.client_ids),
                "client_ids_count": len(request.client_ids) if request.client_ids else 0,
                "limit": request.limit or 100
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
                    client_data=client_data
                )
                
                messages.append(message)
                
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
            try:
                # Создаем директорию для сохранения результатов, если её нет
                # Используем абсолютный путь относительно корня проекта
                project_root = Path(__file__).parent.parent.parent  # backend/app/api -> backend -> project root
                save_dir = project_root / "backend" / "generated_messages"
                save_dir.mkdir(parents=True, exist_ok=True)
                
                # Формируем имя файла с timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                event_type = request.event.type or "unknown"
                # Очищаем имя события от недопустимых символов для имени файла
                safe_event_type = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in event_type)
                filename = f"messages_{safe_event_type}_{timestamp}.json"
                filepath = save_dir / filename
                
                # Сохраняем в JSON файл
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(response_data, f, ensure_ascii=False, indent=2, default=str)
                
                logger.info(f"✅ Сохранено {len(serialized_messages)} сообщений в файл: {filepath}")
                
                # Добавляем путь к файлу в ответ
                response_data["saved_file"] = str(filepath)
                response_data["saved_file_name"] = filename
            except Exception as save_error:
                logger.warning(f"Не удалось сохранить файл: {save_error}")
                # Продолжаем, даже если сохранение не удалось
            
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
