from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
import hashlib

# См. комментарий в llm_service.py — используем cwd для поиска корневого .env
load_dotenv(find_dotenv(usecwd=True), override=False)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")


class VectorService:
    def __init__(self):
        self.client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY if QDRANT_API_KEY else None
        )
        self.openai_client = None
        # Выбор embedding модели:
        # - OpenAI: "text-embedding-3-small"
        # - OpenRouter (OpenAI-compatible): обычно "openai/text-embedding-3-small"
        if EMBEDDING_MODEL:
            self.embedding_model = EMBEDDING_MODEL
        elif OPENAI_API_KEY:
            self.embedding_model = "text-embedding-3-small"
        elif OPENROUTER_API_KEY:
            self.embedding_model = "openai/text-embedding-3-small"
        else:
            self.embedding_model = None

        # Embeddings:
        # - Prefer OpenAI if OPENAI_API_KEY set
        # - Fallback to OpenRouter (OpenAI-compatible API) if OPENROUTER_API_KEY set
        if OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        elif OPENROUTER_API_KEY:
            self.openai_client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": "https://glame.ai",
                    "X-Title": "GLAME AI Platform",
                },
            )
        self._ensure_collections()

    @property
    def allowed_collections(self) -> List[str]:
        # Единый список доменов знаний (можно расширять без миграций)
        return [
            "brand_philosophy",
            "product_knowledge",
            "collections_info",
            "buyer_psychology",
            "sales_playbook",
            "looks_descriptions",
            "content_pieces",
            "persona_knowledge",
            "client_requirements",  # Правила и требования клиентов для генерации образов
        ]

    def ensure_collection(self, collection_name: str):
        """Создать коллекцию если её нет (или пропустить, если уже есть)."""
        try:
            self.client.get_collection(collection_name)
            return
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                try:
                    self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
                    )
                except Exception as create_error:
                    if "409" not in str(create_error) and "already exists" not in str(create_error).lower():
                        raise
            else:
                # если это ошибка несовместимости клиента/сервера — не падаем
                return
    
    def _create_embedding(self, text: str) -> List[float]:
        """Создание embedding для текста через OpenAI"""
        if not self.openai_client or not self.embedding_model:
            raise ValueError(
                "Не настроен провайдер embeddings. "
                "Установите OPENAI_API_KEY или OPENROUTER_API_KEY (OpenAI-compatible) "
                "и при необходимости EMBEDDING_MODEL."
            )
        
        # Пробуем основную модель; если OpenRouter и модель не поддерживается — пробуем запасные варианты.
        models_to_try = [self.embedding_model]
        if OPENROUTER_API_KEY:
            # Частые варианты имен моделей в OpenRouter
            for m in ["openai/text-embedding-3-small", "text-embedding-3-small", "openai/text-embedding-3-large"]:
                if m not in models_to_try:
                    models_to_try.append(m)

        last_err: Optional[Exception] = None
        for model_name in models_to_try:
            try:
                response = self.openai_client.embeddings.create(
                    model=model_name,
                    input=text
                )
                return response.data[0].embedding
            except Exception as e:
                last_err = e
                continue

        raise ValueError(f"Не удалось создать embedding (models tried: {models_to_try}). Last error: {last_err}")
    
    def _generate_document_id(self, text: str, prefix: str = "") -> str:
        """Генерация уникального ID для документа на основе текста"""
        content = f"{prefix}{text}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _ensure_collections(self):
        """Создание коллекций если их нет"""
        collections = self.allowed_collections
        
        for collection_name in collections:
            try:
                self.client.get_collection(collection_name)
                # Коллекция уже существует, пропускаем
            except Exception as e:
                # Проверяем, что это действительно ошибка "не найдено", а не другая
                error_str = str(e).lower()
                if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                    try:
                        # Создаем коллекцию с размерностью 1536 (для OpenAI embeddings)
                        self.client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
                        )
                    except Exception as create_error:
                        # Если коллекция уже существует (409 Conflict), игнорируем
                        if "409" not in str(create_error) and "already exists" not in str(create_error).lower():
                            # Другая ошибка - логируем, но не падаем
                            print(f"Warning: Could not create collection {collection_name}: {create_error}")
                # Для других ошибок (например, проблемы с версией Qdrant) просто игнорируем
    
    def add_document(
        self,
        collection_name: str,
        document_id: str,
        vector: List[float],
        payload: Dict
    ):
        """Добавление документа в векторную БД"""
        self.client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=document_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )
    
    def add_text_document(
        self,
        collection_name: str,
        text: str,
        metadata: Optional[Dict] = None,
        document_id: Optional[str] = None
    ):
        """Добавление текстового документа с автоматическим созданием embedding"""
        # гарантируем, что коллекция существует
        self.ensure_collection(collection_name)
        if document_id is None:
            document_id = self._generate_document_id(text, collection_name)
        
        vector = self._create_embedding(text)
        payload = {
            "text": text,
            **(metadata or {})
        }
        
        self.add_document(
            collection_name=collection_name,
            document_id=document_id,
            vector=vector,
            payload=payload
        )
        
        return document_id

    def add_knowledge(
        self,
        collection_name: str,
        text: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """Универсальная запись знания в указанную коллекцию."""
        payload_metadata = {
            "category": category,
            "source": source,
            **(metadata or {})
        }

        return self.add_text_document(
            collection_name=collection_name,
            text=text,
            metadata=payload_metadata
        )
    
    def add_brand_knowledge(
        self,
        text: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Добавление знания о бренде в коллекцию brand_philosophy"""
        payload_metadata = {
            "category": category,
            "source": source,
            **(metadata or {})
        }
        
        return self.add_text_document(
            collection_name="brand_philosophy",
            text=text,
            metadata=payload_metadata
        )
    
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: float = 0.7,
        filter: Optional[Dict] = None
    ) -> List[Dict]:
        """Поиск похожих документов"""
        results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=filter
        )
        
        return [
            {
                "id": result.id,
                "score": result.score,
                "payload": result.payload
            }
            for result in results
        ]

    def retrieve_points(self, collection_name: str, ids: List[str]) -> List[Dict]:
        """Получить точки по id (payload содержит text, category, source для переноса в другую коллекцию)."""
        if not ids:
            return []
        try:
            records = self.client.retrieve(
                collection_name=collection_name,
                ids=ids,
                with_payload=True,
                with_vectors=False,
            )
            return [{"id": r.id, "payload": r.payload or {}} for r in records]
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"retrieve_points {collection_name}: {e}")
            return []
    
    def get_context(self, collection_name: str, query_text: str, limit: int = 3, score_threshold: float = 0.5) -> List[Dict]:
        """Получение релевантного контекста из указанной коллекции"""
        if not self.openai_client:
            # Если нет OpenAI API ключа, возвращаем пустой список (не падаем)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("No OpenAI/OpenRouter API key set - returning empty context")
            return []
        
        try:
            self.ensure_collection(collection_name)
            query_vector = self._create_embedding(query_text)
            # Для коллекций используем более низкий порог, чтобы находить больше результатов
            threshold = 0.3 if collection_name == "collections_info" else score_threshold
            results = self.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=threshold
            )
            return results
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error getting context from {collection_name}: {e}")
            return []

    def get_brand_context(
        self,
        query_text: str,
        limit: int = 3,
        score_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Получение контекста бренда из brand_philosophy с улучшенным поиском
        
        Args:
            query_text: Поисковый запрос
            limit: Максимальное количество результатов
            score_threshold: Минимальный порог релевантности
        """
        return self.get_context("brand_philosophy", query_text, limit=limit, score_threshold=score_threshold)


# Singleton instance
vector_service = VectorService()
