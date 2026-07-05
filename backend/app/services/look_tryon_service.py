import os
import base64
import httpx
import json
import tempfile
from io import BytesIO
from typing import Dict, Optional, List, Any
from uuid import UUID
from pathlib import Path
import logging
from datetime import datetime
from PIL import Image

from dotenv import load_dotenv, find_dotenv
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.services.llm_service import llm_service
from app.services.photo_analysis_orchestrator import photo_analysis_orchestrator

load_dotenv(find_dotenv(usecwd=True), override=False)

logger = logging.getLogger(__name__)

TRY_ON_API_KEY = os.getenv("TRY_ON_API_KEY")
TRY_ON_API_URL = os.getenv("TRY_ON_API_URL", "https://api.replicate.com/v1")
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

# Директория для локального хранения изображений
LOCAL_STORAGE_PATH = Path(__file__).resolve().parents[2] / "uploads" / "tryon"


class LookTryOnService:
    """Сервис для анализа фото пользователя и визуальной примерки образов"""
    
    def __init__(self):
        self.api_key = TRY_ON_API_KEY
        self.api_url = TRY_ON_API_URL
        self.storage_type = STORAGE_TYPE
        
        # Создаем директорию для локального хранения
        if self.storage_type == "local":
            LOCAL_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    
    async def analyze_photo(self, photo_data: bytes, filename: Optional[str] = None) -> Dict:
        return await photo_analysis_orchestrator.analyze_photo(
            photo_data=photo_data,
            filename=filename,
            legacy_provider=self._legacy_analyze_photo,
        )

    async def _legacy_analyze_photo(self, photo_data: bytes, filename: Optional[str] = None) -> Dict:
        """
        Анализ фото пользователя (цветотип, стиль, тип внешности)
        
        Args:
            photo_data: Байты изображения
            filename: Имя файла (опционально)
        
        Returns:
            Dict: Результат анализа с полями:
                - color_type: цветотип (весна, лето, осень, зима)
                - style: стиль внешности
                - features: особенности внешности
                - recommendations: рекомендации по стилю
        """
        try:
            # Legacy fallback: vision-LLM анализ сохраняется как backup path,
            # пока production pipeline не вынесен в отдельный ML inference service.
            image_base64 = base64.b64encode(photo_data).decode('utf-8')
            
            # Используем vision model для анализа (если доступен через OpenRouter)
            # Для этого нужна модель с поддержкой vision (например, GPT-4 Vision)
            prompt = """Проанализируй это фото человека и определи:

1. Цветотип (весна, лето, осень, зима) - на основе цвета кожи, волос, глаз
2. Стиль внешности (романтичный, деловой, спортивный, классический, творческий)
3. Особенности внешности (форма лица, цвет волос, цвет глаз, тон кожи)
4. Рекомендации по стилю украшений (какие цвета металлов, камней, стили подойдут)

Ответь в формате JSON:
{
  "color_type": "цветотип",
  "style": "стиль",
  "features": {
    "face_shape": "форма лица",
    "hair_color": "цвет волос",
    "eye_color": "цвет глаз",
    "skin_tone": "тон кожи"
  },
  "recommendations": {
    "metal_colors": ["рекомендуемые цвета металлов"],
    "stone_colors": ["рекомендуемые цвета камней"],
    "styles": ["рекомендуемые стили"]
  }
}"""

            # Пытаемся использовать vision model через OpenRouter
            # Если vision model недоступна, используем текстовый анализ
            try:
                # Для vision models нужен специальный формат запроса
                analysis = await self._analyze_with_vision_model(image_base64, prompt)
                logger.info("Анализ фото выполнен через vision model")
            except Exception as e:
                logger.debug(f"Vision model недоступна, используем текстовый анализ: {e}")
                analysis = await self._analyze_with_text_fallback(photo_data, filename)
            
            return analysis
        except Exception as e:
            logger.error(f"Ошибка при анализе фото: {e}")
            # Возвращаем базовый анализ
            return {
                "color_type": "универсальный",
                "style": "классический",
                "features": {
                    "face_shape": "овальное",
                    "hair_color": "не определен",
                    "eye_color": "не определен",
                    "skin_tone": "средний"
                },
                "recommendations": {
                    "metal_colors": ["золото", "серебро"],
                    "stone_colors": ["универсальные"],
                    "styles": ["классический", "элегантный"]
                }
            }
    
    async def _analyze_with_vision_model(self, image_base64: str, prompt: str) -> Dict:
        """Анализ через vision model (если доступен)"""
        # Используем LLM сервис для запроса к vision model через OpenRouter
        # OpenRouter поддерживает vision models через стандартный формат messages
        
        try:
            # Получаем модель из настроек или используем дефолтную с поддержкой vision
            vision_model = os.getenv("VISION_MODEL", "openai/gpt-4o")  # GPT-4o имеет поддержку vision
            
            # Формируем сообщение с изображением для vision model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]
            
            # Используем httpx для прямого запроса к OpenRouter
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY не установлен")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://glame.ai",
                        "X-Title": "GLAME AI Platform",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": vision_model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 1000
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                # Извлекаем ответ
                content = result["choices"][0]["message"]["content"]
                
                # Парсим JSON из ответа
                import json
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                else:
                    raise ValueError("Не удалось распарсить ответ vision model")
                    
        except Exception as e:
            logger.debug(f"Vision model недоступна или произошла ошибка: {e}")
            raise  # Пробрасываем исключение для использования fallback
    
    async def _analyze_with_text_fallback(self, photo_data: bytes, filename: Optional[str] = None) -> Dict:
        """Текстовый анализ через LLM (fallback)"""
        prompt = """Проанализируй описание внешности человека и дай рекомендации по стилю украшений.

Учти общие принципы:
- Для светлой кожи и светлых волос подходят холодные оттенки (серебро, белое золото)
- Для теплой кожи и темных волос подходят теплые оттенки (желтое золото, медь)
- Классический стиль подходит всем
- Романтичный стиль подходит для овальных и круглых лиц

Ответь в формате JSON:
{
  "color_type": "универсальный",
  "style": "классический",
  "features": {},
  "recommendations": {
    "metal_colors": ["золото", "серебро"],
    "stone_colors": ["универсальные"],
    "styles": ["классический", "элегантный"]
  }
}"""

        response = await llm_service.generate(
            prompt=prompt,
            system_prompt="Ты эксперт по стилю. Отвечай только валидным JSON.",
            temperature=0.7,
            max_tokens=1000
        )
        
        import json
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            raise ValueError("Не удалось распарсить ответ LLM")
    
    async def generate_tryon_image(
        self,
        user_photo_url: str,
        product_images: List[str],
        look_id: UUID
    ) -> str:
        """
        Генерация изображения с примеркой украшений на фото пользователя
        
        Args:
            user_photo_url: URL фото пользователя
            product_images: Список URL изображений товаров для примерки
            look_id: ID образа
        
        Returns:
            str: URL сгенерированного изображения с примеркой
        """
        try:
            # Пытаемся использовать внешний API для визуальной примерки
            if self.api_key:
                try:
                    try_on_url = await self._generate_with_api(
                        user_photo_url=user_photo_url,
                        product_images=product_images
                    )
                    if try_on_url:
                        return try_on_url
                except Exception as e:
                    logger.warning(f"Ошибка при использовании API примерки: {e}")
            
            # Fallback: возвращаем композицию изображений
            # В реальной реализации здесь может быть собственная модель или другой сервис
            logger.info("Используем fallback для примерки")
            composite_url = await self._generate_composite_image(
                user_photo_url=user_photo_url,
                product_images=product_images,
                look_id=look_id
            )
            
            return composite_url
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения примерки: {e}")
            # Возвращаем оригинальное фото пользователя
            return user_photo_url
    
    async def _generate_with_api(
        self,
        user_photo_url: str,
        product_images: List[str]
    ) -> Optional[str]:
        """
        Генерация через внешний API (например, Replicate)
        
        Это заглушка для реальной интеграции с API визуальной примерки
        """
        # Пример интеграции с Replicate API для модели outfit-anyone
        # В реальной реализации здесь будет запрос к конкретному API
        
        model = "lucataco/outfit-anyone"  # Пример модели
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Запускаем prediction
                response = await client.post(
                    f"{self.api_url}/predictions",
                    headers={
                        "Authorization": f"Token {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "version": "latest",
                        "input": {
                            "person_image": user_photo_url,
                            "garment_images": product_images[:3]  # Максимум 3 товара
                        }
                    }
                )
                response.raise_for_status()
                prediction = response.json()
                
                # Ждем завершения обработки
                prediction_id = prediction.get("id")
                if prediction_id:
                    # В реальной реализации здесь будет polling статуса
                    # Пока возвращаем None для использования fallback
                    return None
        except Exception as e:
            logger.error(f"Ошибка при запросе к API примерки: {e}")
        
        return None
    
    async def _generate_composite_image(
        self,
        user_photo_url: str,
        product_images: List[str],
        look_id: UUID
    ) -> str:
        """
        Генерация композитного изображения (fallback)
        
        В реальной реализации здесь может быть простая композиция изображений
        или использование другой библиотеки для обработки изображений
        """
        # Сохраняем информацию о композиции
        # В реальной реализации здесь будет создание композитного изображения
        # Пока возвращаем URL оригинального фото
        return user_photo_url
    
    async def save_user_photo(
        self,
        photo_data: bytes,
        user_id: UUID,
        filename: Optional[str] = None
    ) -> str:
        """
        Сохранение загруженного фото пользователя
        
        Args:
            photo_data: Байты изображения
            user_id: ID пользователя
            filename: Имя файла
        
        Returns:
            str: URL сохраненного изображения
        """
        try:
            photo_data = self._normalize_photo_to_jpeg(photo_data)
            filename = await self._stable_photo_filename(user_id, filename)
            
            if self.storage_type == "s3":
                url = await self._save_to_s3(photo_data, filename, user_id)
            else:
                url = await self._save_locally(photo_data, filename, user_id)
            
            return url
        except Exception as e:
            logger.error(f"Ошибка при сохранении фото пользователя: {e}")
            raise
    
    async def _save_locally(
        self,
        photo_data: bytes,
        filename: str,
        user_id: UUID
    ) -> str:
        """Сохранение локально"""
        user_folder = await self._user_storage_folder(user_id)
        user_dir = LOCAL_STORAGE_PATH / user_folder
        user_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_user_storage(user_dir)
        
        file_path = user_dir / filename
        file_path.write_bytes(photo_data)
        
        # Возвращаем относительный URL (в реальной реализации нужен абсолютный)
        return f"/uploads/tryon/{user_folder}/{filename}"

    async def save_photo_analysis_artifacts(
        self,
        photo_url: str,
        payload: dict[str, Any],
    ) -> str | None:
        if self.storage_type != "local":
            logger.info("Photo analysis sidecar is skipped for storage_type=%s", self.storage_type)
            return None

        photo_path = self._local_path_from_url(photo_url)
        if photo_path is None:
            logger.warning("Не удалось определить локальный путь для photo_url=%s", photo_url)
            return None

        analysis_path = photo_path.with_name(f"{photo_path.stem}.analysis.json")
        analysis_payload = {
            "schema": "photo-analysis-sidecar/v1",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "photo_url": photo_url,
            "photo_filename": photo_path.name,
            "quality_status": payload.get("quality_status"),
            "can_continue": payload.get("can_continue"),
            "retry_hint": payload.get("retry_hint"),
            "human_readable": payload.get("human_readable", {}),
            "user_facing": payload.get("user_facing", {}),
            "analysis": payload.get("analysis", {}),
            "recommendations": payload.get("recommendations", {}),
            "recommended_products": payload.get("recommended_products", []),
        }
        self._safe_write_json(analysis_path, analysis_payload)
        return f"/uploads/tryon/{photo_path.parent.name}/{analysis_path.name}"
    
    async def _save_to_s3(
        self,
        photo_data: bytes,
        filename: str,
        user_id: UUID
    ) -> str:
        """Сохранение в S3"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=S3_ACCESS_KEY,
                aws_secret_access_key=S3_SECRET_KEY
            )
            
            user_folder = await self._user_storage_folder(user_id)
            key = f"tryon/{user_folder}/{filename}"
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=key,
                Body=photo_data,
                ContentType='image/jpeg'
            )
            
            # Генерируем URL
            url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{key}"
            return url
        except ImportError:
            logger.error("boto3 не установлен для работы с S3")
            raise
        except Exception as e:
            logger.error(f"Ошибка при сохранении в S3: {e}")
            raise

    async def _stable_photo_filename(
        self,
        user_id: UUID,
        original_filename: Optional[str],
    ) -> str:
        user_folder = await self._user_storage_folder(user_id)
        return f"{user_folder}.jpg"

    async def _user_storage_folder(self, user_id: UUID) -> str:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("Не удалось получить пользователя для папки tryon: %s", exc)
            user = None

        raw_folder = (
            getattr(user, "discount_card_number", None)
            or str(user_id)
        )
        normalized = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_"
            for ch in str(raw_folder).strip()
        ).strip("_")
        return normalized or str(user_id)

    def _local_path_from_url(self, photo_url: str) -> Path | None:
        prefix = "/uploads/tryon/"
        if not photo_url.startswith(prefix):
            return None
        relative = photo_url[len(prefix):].strip("/")
        if not relative:
            return None
        return LOCAL_STORAGE_PATH / relative

    def _normalize_photo_to_jpeg(self, photo_data: bytes) -> bytes:
        with Image.open(BytesIO(photo_data)) as img:
            if img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            ):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
                converted = background
            else:
                converted = img.convert("RGB")

            output = BytesIO()
            converted.save(output, format="JPEG", quality=92, optimize=True)
            return output.getvalue()

    def _cleanup_user_storage(self, user_dir: Path) -> None:
        if not user_dir.exists():
            return
        allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".json"}
        for path in user_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_suffixes:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as exc:
                logger.warning("Не удалось удалить старый файл %s: %s", path, exc)

    def _safe_write_json(self, filepath: Path, payload: dict[str, Any]) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(filepath.parent),
            delete=False,
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2, default=str)
            tmp.flush()
            temp_name = tmp.name
        Path(temp_name).replace(filepath)


# Singleton instance
look_tryon_service = LookTryOnService()
