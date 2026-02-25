from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
import json
import logging
from datetime import datetime
from app.database.connection import get_db
from app.services.vector_service import vector_service
from app.services.pdf_processor import pdf_processor
from app.models.knowledge_document import KnowledgeDocument
from app.models.product import Product

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class SyncProductsToKnowledgeResponse(BaseModel):
    success: bool
    collection_name: str
    total_products: int
    synced: int
    failed: int
    errors: List[str] = []

@router.get("/debug/env")
async def debug_env():
    """Диагностика окружения (каким Python запущен backend и доступны ли PDF-библиотеки)."""
    import sys
    import importlib.util
    import os
    from app.services import pdf_processor as pdf_mod
    from app.services.vector_service import vector_service

    def has_pkg(name: str) -> bool:
        return importlib.util.find_spec(name) is not None

    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "openrouter_api_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
        "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "embedding_model": getattr(vector_service, "embedding_model", None),
        "pdfplumber_available": bool(getattr(pdf_mod, "PDFPLUMBER_AVAILABLE", False)),
        "pypdf2_available": bool(getattr(pdf_mod, "PYPDF2_AVAILABLE", False)),
        "pdfplumber_installed": has_pkg("pdfplumber"),
        "pypdf2_installed": has_pkg("PyPDF2"),
    }


class KnowledgeItem(BaseModel):
    text: str
    category: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[dict] = None


class KnowledgeUploadRequest(BaseModel):
    items: List[KnowledgeItem]


class KnowledgeUploadResponse(BaseModel):
    success: bool
    message: str
    uploaded_count: int
    document_ids: List[str]
    document_id: Optional[str] = None  # ID записи в БД


class BatchFileResult(BaseModel):
    filename: str
    success: bool
    message: Optional[str] = None
    uploaded_count: int = 0
    document_id: Optional[str] = None
    document_ids: List[str] = []


class KnowledgeBatchUploadResponse(BaseModel):
    total_files: int
    succeeded: int
    failed: int
    results: List[BatchFileResult]


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size: Optional[int]
    source: Optional[str]
    collection_name: str
    total_items: int
    uploaded_items: int
    failed_items: int
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge(
    request: KnowledgeUploadRequest,
    collection_name: str = Query("brand_philosophy"),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка базы знаний о бренде через API"""
    try:
        document_ids = []
        
        for item in request.items:
            doc_id = vector_service.add_knowledge(
                collection_name=collection_name,
                text=item.text,
                category=item.category,
                source=item.source,
                metadata=item.metadata
            )
            document_ids.append(doc_id)
        
        return KnowledgeUploadResponse(
            success=True,
            message=f"Успешно загружено {len(document_ids)} документов",
            uploaded_count=len(document_ids),
            document_ids=document_ids
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при загрузке базы знаний: {str(e)}"
        )


@router.post("/sync/products", response_model=SyncProductsToKnowledgeResponse)
async def sync_products_to_knowledge(
    collection_name: str = Query("product_knowledge"),
    only_active: bool = Query(True),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """
    Синхронизация товаров из Postgres в Qdrant (коллекция product_knowledge).

    Используется, чтобы агенты могли семантически искать по товарам (описания/теги/категории).
    """
    # embeddings провайдер обязателен для записи в Qdrant (иначе _create_embedding упадет)
    if not getattr(vector_service, "openai_client", None) or not getattr(vector_service, "embedding_model", None):
        raise HTTPException(
            status_code=400,
            detail=(
                "Embeddings провайдер не настроен. "
                "Установите OPENAI_API_KEY или OPENROUTER_API_KEY (и при необходимости EMBEDDING_MODEL), "
                "перезапустите backend."
            ),
        )

    if collection_name not in getattr(vector_service, "allowed_collections", []) and collection_name != "product_knowledge":
        # разрешаем product_knowledge даже если список изменился, но защищаем от опечаток
        raise HTTPException(status_code=400, detail=f"Unsupported collection_name: {collection_name}")

    try:
        q = select(Product)
        if only_active:
            q = q.where(Product.is_active == True)
        q = q.limit(limit)

        result = await db.execute(q)
        products = list(result.scalars().all())

        synced = 0
        failed = 0
        errors: List[str] = []

        for p in products:
            try:
                tags = ", ".join(p.tags) if isinstance(p.tags, list) and p.tags else ""
                text_parts = [
                    f"Название: {p.name}",
                    f"Бренд: {p.brand}" if p.brand else None,
                    f"Категория: {p.category}" if p.category else None,
                    f"Теги: {tags}" if tags else None,
                    f"Описание: {p.description}" if p.description else None,
                ]
                text = "\n".join([x for x in text_parts if x])

                vector_service.add_knowledge(
                    collection_name=collection_name,
                    text=text,
                    category="product",
                    source="postgres",
                    metadata={
                        "product_id": str(p.id),
                        "name": p.name,
                        "brand": p.brand,
                        "category": p.category,
                        "price": p.price,
                        "tags": p.tags,
                        "external_id": p.external_id,
                        "external_code": p.external_code,
                    },
                )
                synced += 1
            except Exception as e:
                failed += 1
                if len(errors) < 10:
                    errors.append(f"{p.name}: {str(e)}")

        return SyncProductsToKnowledgeResponse(
            success=(failed == 0),
            collection_name=collection_name,
            total_products=len(products),
            synced=synced,
            failed=failed,
            errors=errors,
        )
    except Exception as e:
        logger.exception("sync_products_to_knowledge failed")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Ошибка синхронизации товаров в базу знаний: {str(e)}. "
                "Проверьте: 1) Postgres доступен и таблица products актуальна (миграции), "
                "2) Qdrant доступен, 3) настроены embeddings ключи (OPENROUTER_API_KEY/OPENAI_API_KEY)."
            ),
        )


@router.post("/upload/file", response_model=KnowledgeUploadResponse)
async def upload_knowledge_from_file(
    file: UploadFile = File(...),
    collection_name: str = Query("brand_philosophy"),
    replace_duplicates: bool = Query(False, description="Если True — заменить существующий документ с тем же именем"),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка базы знаний о бренде из JSON или PDF файла"""
    logger.info(f"Starting file upload: {file.filename}")
    filename = file.filename or "unknown"

    # Проверка дубликата: такой же filename в этой коллекции
    dup_result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.collection_name == collection_name,
            KnowledgeDocument.filename == filename
        )
    )
    existing = dup_result.scalars().all()
    if existing:
        if not replace_duplicates:
            raise HTTPException(
                status_code=409,
                detail=f"Файл «{filename}» уже есть в этой коллекции. Используйте замену (replace_duplicates=true) или выберите «Заменить» в интерфейсе."
            )
        for doc in existing:
            await _delete_document_by_id(db, doc.id)
    
    # Создаем запись о загрузке
    doc_record = KnowledgeDocument(
        filename=filename,
        file_type="pdf" if filename.lower().endswith('.pdf') else "json",
        file_size=0,
        status="processing",
        collection_name=collection_name,
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)
    
    logger.info(f"Created document record with ID: {doc_record.id}")
    
    try:
        # Читаем файл
        logger.info("Reading file content...")
        content = await file.read()
        filename = file.filename or "unknown"
        file_size = len(content)
        logger.info(f"File read: {filename}, size: {file_size} bytes")
        
        # Обновляем размер файла
        doc_record.file_size = file_size
        await db.commit()
        
        # Определяем тип файла
        is_pdf = filename.lower().endswith('.pdf') or file.content_type == 'application/pdf'
        logger.info(f"File type detected: {'PDF' if is_pdf else 'JSON'}")
        
        if is_pdf:
            # Обработка PDF файла
            logger.info("Starting PDF processing...")
            knowledge_items = await pdf_processor.process_pdf(content, filename=filename)
            logger.info(f"PDF processing completed. Extracted {len(knowledge_items)} knowledge items")
            
            if not knowledge_items:
                doc_record.status = "failed"
                doc_record.error_message = "Не удалось извлечь знания из PDF файла"
                await db.commit()
                raise ValueError("Не удалось извлечь знания из PDF файла")
            
            document_ids = []
            failed_count = 0
            first_error: Optional[str] = None
            
            logger.info(f"Uploading {len(knowledge_items)} knowledge items to vector database...")
            for idx, item in enumerate(knowledge_items):
                try:
                    doc_id = vector_service.add_knowledge(
                        collection_name=collection_name,
                        text=item.get("text", ""),
                        category=item.get("category"),
                        source=item.get("source") or filename,
                        metadata=item.get("metadata")
                    )
                    document_ids.append(doc_id)
                    if (idx + 1) % 10 == 0:
                        logger.info(f"Uploaded {idx + 1}/{len(knowledge_items)} items...")
                except Exception as e:
                    failed_count += 1
                    if first_error is None:
                        first_error = str(e)
                    logger.error(f"Ошибка при загрузке элемента {idx + 1}: {e}")

            # Если ничего не загрузилось — считаем загрузку неуспешной и возвращаем понятную ошибку
            if len(document_ids) == 0 and failed_count > 0:
                doc_record.total_items = len(knowledge_items)
                doc_record.uploaded_items = 0
                doc_record.failed_items = failed_count
                doc_record.status = "failed"
                doc_record.error_message = first_error or "Не удалось загрузить знания в векторную БД"
                await db.commit()
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Не удалось загрузить знания (ошибок: {failed_count}). "
                        f"Первая ошибка: {doc_record.error_message}. "
                        f"Проверьте OPENROUTER_API_KEY/OPENAI_API_KEY и модель embeddings."
                    )
                )
            
            # Обновляем запись
            doc_record.total_items = len(knowledge_items)
            doc_record.uploaded_items = len(document_ids)
            doc_record.failed_items = failed_count
            doc_record.vector_document_ids = document_ids
            doc_record.status = "completed"
            doc_record.source = filename
            await db.commit()
            
            return KnowledgeUploadResponse(
                success=True,
                message=f"PDF обработан: извлечено {len(knowledge_items)}, загружено {len(document_ids)}, ошибок {failed_count}",
                uploaded_count=len(document_ids),
                document_ids=document_ids,
                document_id=str(doc_record.id)
            )
        else:
            # Обработка JSON файла
            try:
                data = json.loads(content.decode('utf-8'))
            except json.JSONDecodeError as e:
                doc_record.status = "failed"
                doc_record.error_message = f"Ошибка парсинга JSON: {str(e)}"
                await db.commit()
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка парсинга JSON: {str(e)}. Поддерживаются только JSON и PDF файлы."
                )
            
            # Поддерживаем два формата:
            # 1. Массив объектов
            # 2. Объект с полем "items" или "knowledge"
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("items", data.get("knowledge", []))
            else:
                doc_record.status = "failed"
                doc_record.error_message = "Неверный формат файла"
                await db.commit()
                raise ValueError("Неверный формат файла. Ожидается массив или объект с полем 'items'")
            
            document_ids = []
            failed_count = 0
            
            for item_data in items:
                try:
                    # Поддерживаем как объекты KnowledgeItem, так и простые строки
                    if isinstance(item_data, str):
                        text = item_data
                        category = None
                        source = None
                        metadata = None
                    else:
                        text = item_data.get("text") or item_data.get("content")
                        if not text:
                            continue
                        category = item_data.get("category")
                        source = item_data.get("source")
                        metadata = item_data.get("metadata")
                    
                    doc_id = vector_service.add_knowledge(
                        collection_name=collection_name,
                        text=text,
                        category=category,
                        source=source or filename,
                        metadata=metadata
                    )
                    document_ids.append(doc_id)
                except Exception as e:
                    failed_count += 1
                    print(f"Ошибка при загрузке элемента: {e}")
            
            # Обновляем запись
            doc_record.total_items = len(items)
            doc_record.uploaded_items = len(document_ids)
            doc_record.failed_items = failed_count
            doc_record.vector_document_ids = document_ids
            doc_record.status = "completed"
            doc_record.source = filename
            await db.commit()
            
            return KnowledgeUploadResponse(
                success=True,
                message=f"Успешно загружено {len(document_ids)} документов из JSON файла",
                uploaded_count=len(document_ids),
                document_ids=document_ids,
                document_id=str(doc_record.id)
            )
    except HTTPException:
        logger.error("HTTPException raised, rolling back...")
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error during file upload: {e}", exc_info=True)
        doc_record.status = "failed"
        doc_record.error_message = str(e)
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при загрузке базы знаний: {str(e)}"
        )


@router.post("/upload/batch", response_model=KnowledgeBatchUploadResponse)
async def upload_knowledge_batch(
    files: List[UploadFile] = File(..., description="PDF или JSON файлы"),
    collection_name: str = Query("brand_philosophy"),
    replace_duplicates: bool = Query(False, description="Если True — заменить существующие документы с теми же именами"),
    db: AsyncSession = Depends(get_db)
):
    """Пакетная загрузка базы знаний из нескольких файлов (папка или выбор файлов)."""
    if not files:
        return KnowledgeBatchUploadResponse(
            total_files=0, succeeded=0, failed=0, results=[]
        )
    results: List[BatchFileResult] = []
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        if not (filename.lower().endswith(".pdf") or filename.lower().endswith(".json")):
            results.append(BatchFileResult(
                filename=filename,
                success=False,
                message="Поддерживаются только PDF и JSON",
            ))
            continue
        # Проверка дубликата
        dup_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.collection_name == collection_name,
                KnowledgeDocument.filename == filename
            )
        )
        existing = dup_result.scalars().all()
        if existing:
            if not replace_duplicates:
                results.append(BatchFileResult(
                    filename=filename,
                    success=False,
                    message="Файл уже в базе. Выберите «Заменить» для перезаписи.",
                ))
                continue
            for doc in existing:
                await _delete_document_by_id(db, doc.id)
        doc_record = KnowledgeDocument(
            filename=filename,
            file_type="pdf" if filename.lower().endswith(".pdf") else "json",
            file_size=0,
            status="processing",
            collection_name=collection_name,
        )
        db.add(doc_record)
        await db.commit()
        await db.refresh(doc_record)
        try:
            content = await upload_file.read()
            file_size = len(content)
            doc_record.file_size = file_size
            await db.commit()
            is_pdf = filename.lower().endswith(".pdf") or (upload_file.content_type or "").startswith("application/pdf")
            if is_pdf:
                knowledge_items = await pdf_processor.process_pdf(content, filename=filename)
                if not knowledge_items:
                    doc_record.status = "failed"
                    doc_record.error_message = "Не удалось извлечь знания из PDF"
                    await db.commit()
                    results.append(BatchFileResult(filename=filename, success=False, message="Не удалось извлечь знания из PDF"))
                    continue
                document_ids = []
                failed_count = 0
                for item in knowledge_items:
                    try:
                        doc_id = vector_service.add_knowledge(
                            collection_name=collection_name,
                            text=item.get("text", ""),
                            category=item.get("category"),
                            source=item.get("source") or filename,
                            metadata=item.get("metadata"),
                        )
                        document_ids.append(doc_id)
                    except Exception as e:
                        failed_count += 1
                        logger.warning(f"Batch item error in {filename}: {e}")
                if not document_ids and failed_count:
                    doc_record.status = "failed"
                    doc_record.error_message = "Не удалось загрузить знания в векторную БД"
                    doc_record.total_items = len(knowledge_items)
                    doc_record.uploaded_items = 0
                    doc_record.failed_items = failed_count
                    await db.commit()
                    results.append(BatchFileResult(filename=filename, success=False, message=doc_record.error_message))
                    continue
                doc_record.total_items = len(knowledge_items)
                doc_record.uploaded_items = len(document_ids)
                doc_record.failed_items = failed_count
                doc_record.vector_document_ids = document_ids
                doc_record.status = "completed"
                doc_record.source = filename
                await db.commit()
                msg = f"PDF: извлечено {len(knowledge_items)}, загружено {len(document_ids)}, ошибок {failed_count}"
                results.append(BatchFileResult(
                    filename=filename, success=True, message=msg,
                    uploaded_count=len(document_ids), document_id=str(doc_record.id), document_ids=document_ids,
                ))
            else:
                try:
                    data = json.loads(content.decode("utf-8"))
                except json.JSONDecodeError as e:
                    doc_record.status = "failed"
                    doc_record.error_message = str(e)
                    await db.commit()
                    results.append(BatchFileResult(filename=filename, success=False, message=f"Ошибка JSON: {e}"))
                    continue
                items = data if isinstance(data, list) else data.get("items", data.get("knowledge", []))
                if not isinstance(items, list):
                    doc_record.status = "failed"
                    doc_record.error_message = "Неверный формат: ожидается массив или объект с items"
                    await db.commit()
                    results.append(BatchFileResult(filename=filename, success=False, message=doc_record.error_message))
                    continue
                document_ids = []
                failed_count = 0
                for item_data in items:
                    try:
                        if isinstance(item_data, str):
                            text, category, source, metadata = item_data, None, None, None
                        else:
                            text = item_data.get("text") or item_data.get("content")
                            if not text:
                                continue
                            category = item_data.get("category")
                            source = item_data.get("source")
                            metadata = item_data.get("metadata")
                        doc_id = vector_service.add_knowledge(
                            collection_name=collection_name,
                            text=text,
                            category=category,
                            source=source or filename,
                            metadata=metadata,
                        )
                        document_ids.append(doc_id)
                    except Exception as e:
                        failed_count += 1
                doc_record.total_items = len(items)
                doc_record.uploaded_items = len(document_ids)
                doc_record.failed_items = failed_count
                doc_record.vector_document_ids = document_ids
                doc_record.status = "completed"
                doc_record.source = filename
                await db.commit()
                results.append(BatchFileResult(
                    filename=filename, success=True,
                    message=f"Загружено {len(document_ids)} из JSON",
                    uploaded_count=len(document_ids), document_id=str(doc_record.id), document_ids=document_ids,
                ))
        except Exception as e:
            logger.exception(f"Batch upload error for {filename}")
            doc_record.status = "failed"
            doc_record.error_message = str(e)
            await db.commit()
            results.append(BatchFileResult(filename=filename, success=False, message=str(e)))
    succeeded = sum(1 for r in results if r.success)
    return KnowledgeBatchUploadResponse(
        total_files=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.get("/search")
async def search_knowledge(
    query: str,
    limit: int = 5,
    score_threshold: float = 0.5,
    collection_name: str = Query("brand_philosophy"),
    db: AsyncSession = Depends(get_db)
):
    """Поиск в базе знаний о бренде"""
    try:
        results = vector_service.get_context(collection_name, query, limit=limit)
        
        # Фильтруем по score_threshold
        filtered_results = [
            r for r in results 
            if r.get("score", 0) >= score_threshold
        ]
        
        return {
            "query": query,
            "results": filtered_results,
            "count": len(filtered_results)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при поиске: {str(e)}"
        )


@router.get("/stats")
async def get_knowledge_stats(collection_name: str = Query("brand_philosophy"), db: AsyncSession = Depends(get_db)):
    """Получение статистики по базе знаний"""
    try:
        # В некоторых версиях Qdrant qdrant-client может падать на валидации ответа (pydantic).
        # Поэтому читаем статистику через REST API Qdrant и парсим JSON вручную.
        import os
        import httpx

        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{qdrant_url}/collections/{collection_name}")
            r.raise_for_status()
            data = r.json().get("result", {})

        vectors = (data.get("config", {}) or {}).get("params", {}).get("vectors", {}) or {}
        return {
            "collection_name": collection_name,
            "total_documents": data.get("points_count", 0) or 0,
            "vector_size": vectors.get("size"),
            "distance": vectors.get("distance"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статистики: {str(e)}"
        )


class CheckDuplicatesResponse(BaseModel):
    duplicates: List[str]  # список имён файлов, которые уже есть в коллекции


@router.get("/documents/check-duplicates", response_model=CheckDuplicatesResponse)
async def check_duplicates(
    collection_name: str = Query("brand_philosophy"),
    filenames: str = Query(..., description="Имена файлов через запятую"),
    db: AsyncSession = Depends(get_db)
):
    """Проверка: какие из переданных имён файлов уже есть в коллекции."""
    names = [n.strip() for n in filenames.split(",") if n.strip()]
    if not names:
        return CheckDuplicatesResponse(duplicates=[])
    result = await db.execute(
        select(KnowledgeDocument.filename).where(
            KnowledgeDocument.collection_name == collection_name,
            KnowledgeDocument.filename.in_(names)
        ).distinct()
    )
    found = [row[0] for row in result.all()]
    return CheckDuplicatesResponse(duplicates=found)


async def _delete_document_by_id(db: AsyncSession, document_id: UUID) -> None:
    """Удаляет документ из БД и его векторы из Qdrant (если не используются другими документами)."""
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        return
    used_elsewhere: set[str] = set()
    if document.vector_document_ids:
        other_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id != document.id,
                KnowledgeDocument.collection_name == document.collection_name
            )
        )
        for d in other_result.scalars().all():
            if d.vector_document_ids:
                used_elsewhere.update([str(x) for x in d.vector_document_ids])
        for doc_id in document.vector_document_ids:
            doc_id_str = str(doc_id)
            if doc_id_str in used_elsewhere:
                continue
            try:
                vector_service.client.delete(
                    collection_name=document.collection_name,
                    points_selector=[doc_id_str]
                )
            except Exception as e:
                logger.warning(f"Qdrant delete point {doc_id_str}: {e}")
    await db.delete(document)
    await db.commit()


@router.get("/documents", response_model=List[KnowledgeDocumentResponse])
async def get_knowledge_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status: Optional[str] = None,
    collection_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Получение истории загрузки документов"""
    try:
        query = select(KnowledgeDocument)
        
        if status:
            query = query.where(KnowledgeDocument.status == status)
        if collection_name:
            query = query.where(KnowledgeDocument.collection_name == collection_name)
        
        query = query.order_by(KnowledgeDocument.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        documents = result.scalars().all()
        return list(documents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении истории: {str(e)}"
        )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_knowledge_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о конкретном документе"""
    try:
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении документа: {str(e)}"
        )


class ChangeCollectionRequest(BaseModel):
    collection_name: str


@router.patch("/documents/{document_id}/collection", response_model=KnowledgeDocumentResponse)
async def change_document_collection(
    document_id: UUID,
    body: ChangeCollectionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Перенос загруженного документа в другую коллекцию (векторы копируются в новую коллекцию, из старой удаляются)."""
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    new_collection = body.collection_name.strip()
    allowed = getattr(vector_service, "allowed_collections", None) or []
    if new_collection not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Коллекция «{new_collection}» не разрешена. Допустимые: {', '.join(allowed)}"
        )
    if document.collection_name == new_collection:
        await db.refresh(document)
        return document
    old_collection = document.collection_name
    ids_old = document.vector_document_ids or []
    if not ids_old:
        document.collection_name = new_collection
        await db.commit()
        await db.refresh(document)
        return document
    ids_old_str = [str(i) for i in ids_old]
    points = vector_service.retrieve_points(old_collection, ids_old_str)
    if not points:
        raise HTTPException(
            status_code=500,
            detail="Не удалось прочитать точки из векторной БД. Коллекция могла быть удалена."
        )
    vector_service.ensure_collection(new_collection)
    new_ids = []
    filename = document.filename or "unknown"
    for rec in points:
        payload = rec.get("payload") or {}
        text = payload.get("text") or ""
        if not text:
            continue
        try:
            doc_id = vector_service.add_knowledge(
                collection_name=new_collection,
                text=text,
                category=payload.get("category"),
                source=payload.get("source") or filename,
                metadata={k: v for k, v in (payload or {}).items() if k not in ("text", "category", "source")},
            )
            new_ids.append(doc_id)
        except Exception as e:
            logger.warning(f"Move collection: add_knowledge failed for one point: {e}")
    for doc_id in ids_old_str:
        try:
            vector_service.client.delete(
                collection_name=old_collection,
                points_selector=[doc_id],
            )
        except Exception as e:
            logger.warning(f"Move collection: delete old point {doc_id}: {e}")
    document.collection_name = new_collection
    document.vector_document_ids = new_ids
    await db.commit()
    await db.refresh(document)
    return document


@router.delete("/documents/{document_id}")
async def delete_knowledge_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Удаление документа из базы знаний"""
    try:
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Удаляем документы из векторной БД (безопасно: не удаляем точки, если они используются в других загрузках)
        deleted_vector_ids: List[str] = []
        skipped_vector_ids: List[str] = []
        if document.vector_document_ids:
            # Собираем все vector ids из других документов той же коллекции
            other_result = await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id != document.id,
                    KnowledgeDocument.collection_name == document.collection_name
                )
            )
            others = other_result.scalars().all()
            used_elsewhere: set[str] = set()
            for d in others:
                if d.vector_document_ids:
                    used_elsewhere.update([str(x) for x in d.vector_document_ids])

            try:
                for doc_id in document.vector_document_ids:
                    doc_id_str = str(doc_id)
                    if doc_id_str in used_elsewhere:
                        skipped_vector_ids.append(doc_id_str)
                        continue
                    vector_service.client.delete(
                        collection_name=document.collection_name,
                        points_selector=[doc_id_str]
                    )
                    deleted_vector_ids.append(doc_id_str)
            except Exception as e:
                print(f"Ошибка при удалении из векторной БД: {e}")
        
        # Удаляем запись из БД
        await db.delete(document)
        await db.commit()
        
        return {
            "success": True,
            "message": f"Документ {document.filename} успешно удален",
            "deleted_vector_ids": deleted_vector_ids,
            "skipped_vector_ids": skipped_vector_ids,
            "collection_name": document.collection_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при удалении документа: {str(e)}"
        )


@router.delete("/collections/{collection_name}/clear")
async def clear_knowledge_collection(
    collection_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Полная очистка коллекции: удаляет все точки из Qdrant и историю загрузок по этой коллекции."""
    try:
        import os
        import httpx

        # 1) Удаляем коллекцию в Qdrant и создаём заново (быстрее/проще, чем удалять все points)
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.delete(f"{qdrant_url}/collections/{collection_name}")
            # recreate
            await client.put(
                f"{qdrant_url}/collections/{collection_name}",
                json={
                    "vectors": {
                        "size": 1536,
                        "distance": "Cosine"
                    }
                }
            )

        # 2) Удаляем историю (knowledge_documents) по этой коллекции
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.collection_name == collection_name))
        docs = result.scalars().all()
        deleted_history = len(docs)
        for d in docs:
            await db.delete(d)
        await db.commit()

        return {
            "success": True,
            "collection_name": collection_name,
            "deleted_history_records": deleted_history,
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка очистки коллекции: {str(e)}")


@router.post("/documents/{document_id}/replace")
async def replace_knowledge_document(
    document_id: UUID,
    file: UploadFile = File(...),
    collection_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Замена документа - удаление старого и загрузка нового"""
    try:
        # Получаем старый документ
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        old_document = result.scalar_one_or_none()
        if not old_document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Удаляем старые документы из векторной БД
        if old_document.vector_document_ids:
            try:
                for doc_id in old_document.vector_document_ids:
                    vector_service.client.delete(
                        collection_name=old_document.collection_name,
                        points_selector=[doc_id]
                    )
            except Exception as e:
                print(f"Ошибка при удалении старых документов из векторной БД: {e}")
        
        # Загружаем новый файл (используем существующую логику)
        content = await file.read()
        filename = file.filename or old_document.filename
        file_size = len(content)
        
        is_pdf = filename.lower().endswith('.pdf') or file.content_type == 'application/pdf'
        
        # Обновляем запись документа
        target_collection = collection_name or old_document.collection_name
        old_document.filename = filename
        old_document.file_type = "pdf" if is_pdf else "json"
        old_document.file_size = file_size
        old_document.status = "processing"
        old_document.error_message = None
        old_document.collection_name = target_collection
        await db.commit()
        
        if is_pdf:
            knowledge_items = await pdf_processor.process_pdf(content, filename=filename)
        else:
            data = json.loads(content.decode('utf-8'))
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("items", data.get("knowledge", []))
            else:
                raise ValueError("Неверный формат файла")
            knowledge_items = items
        
        if not knowledge_items:
            old_document.status = "failed"
            old_document.error_message = "Не удалось извлечь знания из файла"
            await db.commit()
            raise ValueError("Не удалось извлечь знания из файла")
        
        document_ids = []
        failed_count = 0
        
        for item in knowledge_items:
            try:
                if isinstance(item, dict):
                    doc_id = vector_service.add_knowledge(
                        collection_name=target_collection,
                        text=item.get("text", ""),
                        category=item.get("category"),
                        source=item.get("source") or filename,
                        metadata=item.get("metadata")
                    )
                else:
                    doc_id = vector_service.add_knowledge(
                        collection_name=target_collection,
                        text=item if isinstance(item, str) else str(item),
                        source=filename
                    )
                document_ids.append(doc_id)
            except Exception as e:
                failed_count += 1
                print(f"Ошибка при загрузке элемента: {e}")
        
        # Обновляем запись
        old_document.total_items = len(knowledge_items)
        old_document.uploaded_items = len(document_ids)
        old_document.failed_items = failed_count
        old_document.vector_document_ids = document_ids
        old_document.status = "completed"
        old_document.source = filename
        await db.commit()
        
        return {
            "success": True,
            "message": f"Документ успешно заменен. Загружено {len(document_ids)} знаний",
            "uploaded_count": len(document_ids),
            "document_ids": document_ids,
            "document_id": str(old_document.id)
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при замене документа: {str(e)}"
        )
