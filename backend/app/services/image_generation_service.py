import os
import httpx
import base64
import logging
import asyncio
import re
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from pathlib import Path
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """Сервис для генерации изображений образов через AI"""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.api_key = os.getenv("IMAGE_GENERATION_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        self.api_url = os.getenv("IMAGE_GENERATION_API_URL", "https://openrouter.ai/api/v1")
        self.model = os.getenv("IMAGE_GENERATION_MODEL", "black-forest-labs/flux-pro")
        self.storage_type = os.getenv("STORAGE_TYPE", "local")
        self.local_storage_dir = Path("static/look_images")
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)
        self.models_root_dir = Path("static/models")
        self.models_root_dir.mkdir(parents=True, exist_ok=True)
    
    def set_db_session(self, db_session: AsyncSession):
        """Устанавливает сессию БД для сервиса"""
        self.db = db_session
        
        # URL типовой модели GLAME (можно заменить на реальное изображение)
        self.default_model_url = os.getenv(
            "GLAME_DEFAULT_MODEL_URL",
            "/static/default_glame_model.jpg"  # Путь к типовой модели
        )
        
        # Инициализация S3 если нужно
        if self.storage_type == "s3":
            try:
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                    aws_secret_access_key=os.getenv("S3_SECRET_KEY")
                )
                self.s3_bucket_name = os.getenv("S3_BUCKET_NAME")
            except ImportError:
                logger.warning("boto3 not installed, falling back to local storage")
                self.storage_type = "local"
    
    async def _upload_image_to_storage(
        self,
        image_data: bytes,
        filename: str,
        content_type: str = "image/png",
        storage_subdir: str = "look_images",
    ) -> str:
        """Загрузка изображения в хранилище (local или S3)"""
        safe_subdir = (storage_subdir or "look_images").strip().strip("/").replace("\\", "/")
        if not safe_subdir:
            safe_subdir = "look_images"
        if self.storage_type == "s3":
            if not self.s3_bucket_name:
                raise ValueError("S3_BUCKET_NAME is not set")
            try:
                self.s3_client.put_object(
                    Bucket=self.s3_bucket_name,
                    Key=f"{safe_subdir}/{filename}",
                    Body=image_data,
                    ContentType=content_type,
                    ACL='public-read'
                )
                return f"https://{self.s3_bucket_name}.s3.amazonaws.com/{safe_subdir}/{filename}"
            except Exception as e:
                logger.error(f"Error uploading to S3: {e}")
                raise
        else:
            # Local storage
            target_dir = Path("static") / safe_subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / filename
            with open(file_path, "wb") as f:
                f.write(image_data)
            return f"/static/{safe_subdir}/{filename}"
    
    async def _get_model_from_settings(self) -> Optional[str]:
        """Получает модель для генерации изображений из БД настроек"""
        try:
            from sqlalchemy import select
            from app.database.connection import AsyncSessionLocal
            from app.models.app_setting import AppSetting

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AppSetting).where(AppSetting.key == "image_generation_model")
                )
                setting = result.scalar_one_or_none()
                if setting and setting.value:
                    return str(setting.value).strip()
        except Exception:
            return None
        return None

    @staticmethod
    def _sanitize_profile_name(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = re.sub(r"[^a-zA-Z0-9_\- ]+", "", str(value)).strip()
        if not cleaned:
            return None
        return re.sub(r"\s+", "_", cleaned).lower()

    def _discover_model_reference_images(self, model_profile: Optional[str], limit: int = 4) -> List[str]:
        """
        Возвращает список URL референс-фото типажа из static/models.
        Логика:
        1) если указан profile — ищем подпапку profile;
        2) если не найдено — берем первую подпапку;
        3) если подпапок нет — берем изображения из корня static/models.
        """
        try:
            if not self.models_root_dir.exists():
                return []

            exts = {".jpg", ".jpeg", ".png", ".webp"}
            subdirs = sorted([p for p in self.models_root_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
            profile_norm = self._sanitize_profile_name(model_profile)

            selected_dir: Optional[Path] = None
            if profile_norm and subdirs:
                selected_dir = next(
                    (d for d in subdirs if self._sanitize_profile_name(d.name) == profile_norm),
                    None
                )
                if not selected_dir:
                    selected_dir = next(
                        (d for d in subdirs if profile_norm in self._sanitize_profile_name(d.name)),
                        None
                    )

            if not selected_dir and subdirs:
                selected_dir = subdirs[0]

            source_dir = selected_dir or self.models_root_dir
            files = sorted(
                [p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in exts],
                key=lambda p: p.name.lower(),
            )[:limit]
            urls = [f"/static/models/{f.relative_to(self.models_root_dir).as_posix()}" for f in files]

            if urls:
                logger.info(
                    "Using %s model reference images from %s (profile=%s)",
                    len(urls),
                    source_dir.as_posix(),
                    model_profile or "auto",
                )
            else:
                logger.info(
                    "No model reference images found in %s (profile=%s)",
                    source_dir.as_posix(),
                    model_profile or "auto",
                )
            return urls
        except Exception as e:
            logger.warning("Could not discover model reference images: %s", e)
            return []

    async def _generate_with_openrouter(
        self,
        prompt: str,
        model: Optional[str] = None,
        product_images: Optional[List[str]] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Optional[bytes]:
        """Генерация изображения через OpenRouter API с использованием chat/completions и modalities"""
        if not self.api_key:
            logger.warning("No image generation API key set")
            return None
        
        # Пробуем получить модель из настроек БД, затем из env, затем дефолт
        if not model:
            model = await self._get_model_from_settings()
        if not model:
            model = self.model
        
        try:
            # Увеличиваем таймаут до 10 минут для генерации изображений через OpenRouter
            async with httpx.AsyncClient(timeout=600.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://glame.ai",
                    "X-Title": "GLAME AI Platform",
                }
                
                # Формируем messages с референс-изображениями (типаж + товары), если они есть
                messages_content = []
                
                # Сначала используем фото товаров (критично для точной передачи изделий),
                # затем изображения типажа модели.
                image_sources: List[str] = []
                if product_images:
                    image_sources.extend(product_images)
                if reference_images:
                    image_sources.extend(reference_images)

                if image_sources:
                    loaded_images_count = 0
                    for img_url in image_sources[:8]:  # Максимум 8 референсов
                        if not img_url:
                            continue
                        
                        try:
                            img_data = None
                            
                            # Загружаем изображение в зависимости от типа URL
                            if img_url.startswith("http://") or img_url.startswith("https://"):
                                # Внешний URL - загружаем через HTTP
                                img_response = await client.get(img_url, timeout=10.0)
                                img_response.raise_for_status()
                                img_data = img_response.content
                            elif img_url.startswith("/static/"):
                                # Локальный статический файл
                                img_path = Path(img_url.lstrip("/"))
                                if img_path.exists():
                                    img_data = img_path.read_bytes()
                                else:
                                    logger.debug(f"Static file not found: {img_path}")
                                    continue
                            elif img_url.startswith("/uploads/"):
                                # Загруженный файл - пробуем через backend API
                                # Преобразуем относительный путь в полный URL backend
                                backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
                                full_url = f"{backend_url}{img_url}"
                                try:
                                    img_response = await client.get(full_url, timeout=10.0)
                                    img_response.raise_for_status()
                                    img_data = img_response.content
                                except Exception as e:
                                    logger.debug(f"Could not load uploaded file via backend: {full_url}, error: {e}")
                                    # Пробуем как локальный файл
                                    img_path = Path(img_url.lstrip("/"))
                                    if img_path.exists():
                                        img_data = img_path.read_bytes()
                                    else:
                                        continue
                            elif "/uploadson/" in img_url:
                                # Исправляем опечатку uploadson -> uploads
                                corrected_url = img_url.replace("/uploadson/", "/uploads/")
                                backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
                                full_url = f"{backend_url}{corrected_url}"
                                try:
                                    img_response = await client.get(full_url, timeout=10.0)
                                    img_response.raise_for_status()
                                    img_data = img_response.content
                                except Exception:
                                    continue
                            else:
                                # Пробуем как относительный путь к локальному файлу
                                img_path = Path(img_url.lstrip("/"))
                                if img_path.exists():
                                    img_data = img_path.read_bytes()
                                else:
                                    continue
                            
                            if not img_data:
                                continue
                            
                            # Конвертируем в base64
                            img_base64 = base64.b64encode(img_data).decode('utf-8')
                            # Определяем MIME type
                            mime_type = "image/jpeg"
                            img_url_lower = img_url.lower()
                            if img_url_lower.endswith('.png'):
                                mime_type = "image/png"
                            elif img_url_lower.endswith('.webp'):
                                mime_type = "image/webp"
                            elif img_url_lower.endswith('.gif'):
                                mime_type = "image/gif"
                            
                            messages_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{img_base64}"
                                }
                            })
                            loaded_images_count += 1
                            
                        except Exception as e:
                            logger.warning(f"Could not load product image {img_url}: {e}")
                            continue
                    
                    if loaded_images_count > 0:
                        logger.info(f"Successfully loaded {loaded_images_count} reference images for generation")
                    else:
                        logger.warning("No reference images could be loaded, generating without image references")
                
                # Добавляем текстовый промпт
                messages_content.append({
                    "type": "text",
                    "text": prompt
                })
                
                # Формируем payload для генерации изображений через OpenRouter
                # Используем chat/completions с modalities: ["image", "text"]
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": messages_content
                        }
                    ],
                    "modalities": ["image", "text"]
                }
                
                # Для Gemini моделей добавляем image_config
                model_lower = model.lower()
                if "gemini" in model_lower:
                    payload["image_config"] = {
                        "aspect_ratio": "1:1",
                        "image_size": "4K"
                    }
                
                logger.info(f"Отправка запроса на генерацию изображения через OpenRouter (модель: {model})")
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Получен ответ от OpenRouter, проверка наличия изображения...")
                
                # Извлекаем изображение из ответа
                # Формат: result["choices"][0]["message"]["images"][0]["image_url"]["url"]
                choices = result.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    images = message.get("images", [])
                    if images and len(images) > 0:
                        image_data = images[0].get("image_url", {})
                        image_url = image_data.get("url", "")
                        
                        if image_url:
                            logger.info(f"Изображение найдено в ответе OpenRouter, тип: {'base64' if image_url.startswith('data:image') else 'URL'}")
                            # Изображение может быть base64 data URL или обычным URL
                            if image_url.startswith("data:image"):
                                # Извлекаем base64 из data URL
                                base64_data = image_url.split(",")[1]
                                logger.info("Декодирование base64 изображения...")
                                decoded_image = base64.b64decode(base64_data)
                                logger.info(f"Генерация изображения через OpenRouter завершена успешно (размер: {len(decoded_image)} байт)")
                                return decoded_image
                            elif image_url.startswith("http"):
                                # Загружаем изображение по URL
                                logger.info(f"Загрузка изображения по URL: {image_url}")
                                img_response = await client.get(image_url, timeout=120.0)
                                img_response.raise_for_status()
                                image_content = img_response.content
                                logger.info(f"Генерация изображения через OpenRouter завершена успешно (размер: {len(image_content)} байт)")
                                return image_content
                            else:
                                # Пробуем декодировать как base64 напрямую
                                try:
                                    logger.info("Попытка декодирования как base64...")
                                    decoded_image = base64.b64decode(image_url)
                                    logger.info(f"Генерация изображения через OpenRouter завершена успешно (размер: {len(decoded_image)} байт)")
                                    return decoded_image
                                except Exception as e:
                                    logger.warning(f"Could not decode image data from OpenRouter response: {e}")
                    else:
                        logger.warning(f"В ответе OpenRouter нет изображений в message.images")
                else:
                    logger.warning(f"В ответе OpenRouter нет choices")
                
                logger.debug(f"No image found in OpenRouter response for model {model}")
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from OpenRouter image generation API: {e.response.status_code} - {e.response.text[:200]}")
        except Exception as e:
            logger.error(f"Error generating image with OpenRouter: {e}")
        
        return None
    
    async def _generate_with_replicate(
        self,
        prompt: str,
        model: Optional[str] = None
    ) -> Optional[bytes]:
        """Генерация изображения через Replicate API"""
        replicate_api_key = os.getenv("REPLICATE_API_TOKEN")
        if not replicate_api_key:
            return None
        
        try:
            # Используем httpx для прямого вызова Replicate API
            # Это более надежно, чем использование библиотеки replicate
            # Увеличиваем таймаут до 10 минут для генерации изображений через Replicate
            async with httpx.AsyncClient(timeout=600.0) as client:
                # Определяем модель для Replicate
                replicate_model = model or "black-forest-labs/flux-pro"
                # Преобразуем формат модели OpenRouter в формат Replicate
                if "black-forest-labs/flux" in replicate_model.lower():
                    replicate_model = "black-forest-labs/flux-pro"
                elif "google/nano" in replicate_model.lower():
                    # Для Nano используем другую модель или пропускаем
                    return None
                
                # Создаем prediction
                response = await client.post(
                    "https://api.replicate.com/v1/predictions",
                    headers={
                        "Authorization": f"Token {replicate_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "version": "39ed52f2a78e0052dcd0fe653512842ae527a973999cd7884ce010a925577798",  # Flux Pro version
                        "input": {
                            "prompt": prompt,
                            "num_outputs": 1,
                            "aspect_ratio": "1:1",
                            "output_format": "png"
                        }
                    }
                )
                response.raise_for_status()
                prediction = response.json()
                
                prediction_id = prediction.get("id")
                if not prediction_id:
                    return None
                
                # Polling статуса prediction - ждем завершения генерации
                logger.info(f"Начало polling статуса генерации Replicate (prediction_id: {prediction_id})")
                max_attempts = 120  # Увеличено до 120 попыток (4 минуты при интервале 2 сек)
                for attempt in range(max_attempts):
                    if attempt > 0:  # Не ждем перед первой проверкой
                        await asyncio.sleep(2)  # Ждем 2 секунды между проверками
                    
                    status_response = await client.get(
                        f"https://api.replicate.com/v1/predictions/{prediction_id}",
                        headers={
                            "Authorization": f"Token {replicate_api_key}"
                        }
                    )
                    status_response.raise_for_status()
                    status_data = status_response.json()
                    
                    status = status_data.get("status")
                    logger.debug(f"Replicate prediction status (попытка {attempt + 1}/{max_attempts}): {status}")
                    
                    if status == "succeeded":
                        logger.info(f"Генерация изображения через Replicate завершена успешно (попытка {attempt + 1})")
                        output = status_data.get("output")
                        if output:
                            image_url = output[0] if isinstance(output, list) else output
                            # Загружаем изображение
                            logger.info(f"Загрузка сгенерированного изображения по URL: {image_url}")
                            img_response = await client.get(image_url, timeout=60.0)
                            img_response.raise_for_status()
                            image_content = img_response.content
                            logger.info(f"Генерация изображения через Replicate завершена успешно (размер: {len(image_content)} байт)")
                            return image_content
                        else:
                            logger.warning("Replicate вернул статус 'succeeded', но output пуст")
                            return None
                    elif status in ["failed", "canceled"]:
                        error_msg = status_data.get('error', 'Unknown error')
                        logger.error(f"Генерация изображения через Replicate завершилась с ошибкой: {status} - {error_msg}")
                        return None
                    # Если status == "starting" или "processing", продолжаем polling
                    elif status in ["starting", "processing"]:
                        if attempt % 10 == 0:  # Логируем каждые 10 попыток
                            logger.info(f"Генерация изображения через Replicate в процессе... (статус: {status}, попытка {attempt + 1}/{max_attempts})")
                
                logger.warning(f"Генерация изображения через Replicate превысила лимит времени после {max_attempts} попыток")
                return None
                
        except ImportError:
            logger.warning("replicate package not installed, using httpx directly")
        except httpx.HTTPStatusError as e:
            logger.error(f"Replicate API error: {e.response.status_code} - {e.response.text[:200]}")
        except Exception as e:
            logger.error(f"Error generating image with Replicate: {e}")
        
        return None
    
    async def generate_look_image(
        self,
        look_description: Dict[str, Any],
        products: List[Dict[str, Any]],
        use_default_model: bool = False,
        model_profile: Optional[str] = None,
        asset_group: str = "look_images",
        filename_prefix: str = "look",
    ) -> Optional[str]:
        """
        Генерация изображения образа
        
        Args:
            look_description: Описание образа (name, description, style, mood)
            products: Список товаров в образе
            use_default_model: Использовать типовую модель GLAME вместо генерации
        
        Returns:
            URL сгенерированного изображения или None
        """
        if use_default_model:
            # Используем типовую модель GLAME
            return await self._generate_on_default_model(look_description, products)
        
        # Генерируем промпт для AI
        prompt = self._build_image_prompt(look_description, products)
        
        # Собираем URL изображений товаров для включения в генерацию
        product_image_urls = []
        seen_product_urls = set()
        for product in products:
            product_images = product.get("images", [])
            if product_images and isinstance(product_images, list):
                # Берем до 3 фото каждого украшения, чтобы точнее передать форму и посадку.
                for img_url in product_images[:3]:
                    if isinstance(img_url, str) and img_url.strip() and img_url not in seen_product_urls:
                        product_image_urls.append(img_url)
                        seen_product_urls.add(img_url)
        
        model_reference_urls = self._discover_model_reference_images(model_profile=model_profile, limit=4)
        logger.info(
            "Начало генерации изображения образа (типажей: %s, товарных фото: %s, profile=%s)",
            len(model_reference_urls),
            len(product_image_urls),
            model_profile or "auto",
        )
        
        # Получаем модель из настроек
        model = await self._get_model_from_settings() or self.model
        logger.info(f"Используемая модель для генерации изображения: {model}")
        
        # Пробуем разные API и ждем завершения генерации
        image_data = None
        
        # 1. Пробуем OpenRouter (правильный формат с modalities для моделей генерации изображений)
        # Передаем изображения товаров для включения в генерацию
        logger.info("Попытка генерации через OpenRouter...")
        image_data = await self._generate_with_openrouter(
            prompt,
            model,
            product_images=product_image_urls,
            reference_images=model_reference_urls,
        )
        
        # 2. Если не получилось, пробуем Replicate (для Flux и других моделей)
        if not image_data:
            logger.info("Генерация через OpenRouter не удалась, пробуем Replicate...")
            image_data = await self._generate_with_replicate(prompt, model)
        
        # 3. Если не получилось — не возвращаем "пустую" модель,
        # чтобы не вводить в заблуждение изображением без нужных товаров.
        if not image_data:
            logger.warning("AI image generation failed; returning None to avoid product mismatch")
            return None
        
        # Сохраняем изображение
        logger.info("Сохранение сгенерированного изображения...")
        safe_prefix = (filename_prefix or "look").strip().replace(" ", "_")
        filename = f"{safe_prefix}_{uuid4()}.png"
        image_url = await self._upload_image_to_storage(
            image_data,
            filename,
            storage_subdir=asset_group,
        )
        
        logger.info(f"Генерация изображения образа полностью завершена: {image_url}")
        return image_url
    
    def _build_image_prompt(
        self,
        look_description: Dict[str, Any],
        products: List[Dict[str, Any]]
    ) -> str:
        """Построение промпта для генерации изображения образа"""
        name = look_description.get("name", "Образ")
        description = look_description.get("description", "")
        style = look_description.get("style", "")
        mood = look_description.get("mood", "")
        
        # Описание товаров + строгий checklist по обязательной примерке
        def infer_wear_zone(product: Dict[str, Any]) -> str:
            category = str(product.get("category") or "").lower()
            name_text = str(product.get("name") or "").lower()
            source = f"{category} {name_text}"
            if any(token in source for token in ("серьг", "серьги", "earring")):
                return "уши (на обеих ушах, если это пара)"
            if any(token in source for token in ("кольц", "ring")):
                return "пальцы руки"
            if any(token in source for token in ("браслет", "bracelet")):
                return "запястье"
            if any(token in source for token in ("колье", "цеп", "подвес", "necklace", "chain", "pendant")):
                return "шея/декольте"
            return "на модели в естественной зоне ношения"

        product_names = [p.get("name", "") for p in products[:6]]
        must_wear_lines: List[str] = []
        for idx, product in enumerate(products[:6], start=1):
            pname = str(product.get("name") or f"Изделие {idx}").strip()
            pdesc = str(product.get("description") or "").strip()
            wear_zone = infer_wear_zone(product)
            details = f" — {pdesc[:180]}" if pdesc else ""
            must_wear_lines.append(f"{idx}. {pname}{details}. Где видно: {wear_zone}.")
        must_wear_block = "\n".join(must_wear_lines) if must_wear_lines else "Список изделий отсутствует."
        
        prompt = f"""Профессиональная фотография модного образа для украшений GLAME.

Концепция образа: {name}
Стиль: {style}
Настроение: {mood}
Описание: {description}

Украшения в образе: {', '.join(product_names)}

MUST-WEAR (ОБЯЗАТЕЛЬНО НАДЕТЬ И ПОКАЗАТЬ КАЖДОЕ ИЗДЕЛИЕ):
{must_wear_block}

Требования к изображению:
- Высокое качество, профессиональная фотография
- Элегантная модель в стиле GLAME
- Украшения из MUST-WEAR должны быть четко видны и действительно надеты на модели
- Стиль соответствует описанию: {style}
- Настроение: {mood}
- Светлая, чистая композиция
- Фон нейтральный, не отвлекающий внимание от украшений
- Фотография для каталога премиальных украшений
- Модельная съемка: выразительные позы, смелые модные ракурсы, премиальная editorial эстетика
- Сфокусируйся на стиле, пластике позы, свете и композиции
- СТРОГО: используй фото украшений как референсы и собери единый образ ИМЕННО из изделий из MUST-WEAR
- СТРОГО: сохрани характерные формы, фактуру, посадку и оттенки каждого украшения из референсов
- СТРОГО: не добавляй украшения, которых нет в MUST-WEAR
- СТРОГО: не добавляй текст на изображение
- СТРОГО: без надписей, букв, логотипов, watermark, плашек, баннеров

Стиль фотографии: fashion photography, editorial style, luxury jewelry photography"""
        
        return prompt
    
    async def _generate_on_default_model(
        self,
        look_description: Dict[str, Any],
        products: List[Dict[str, Any]]
    ) -> str:
        """
        Генерация изображения образа на типовой модели GLAME
        
        Если есть API для наложения украшений на модель, используем его.
        Иначе возвращаем URL типовой модели.
        """
        # Если есть API для наложения украшений на модель
        try_on_api_key = os.getenv("TRY_ON_API_KEY")
        try_on_api_url = os.getenv("TRY_ON_API_URL")
        
        if try_on_api_key and try_on_api_url:
            # Пробуем использовать API примерки на типовую модель
            product_images = [
                p.get("images", [])[0]
                for p in products
                if p.get("images") and len(p.get("images", [])) > 0
            ]
            
            if product_images:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            f"{try_on_api_url}/tryon",
                            headers={
                                "Authorization": f"Bearer {try_on_api_key}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "person_image_url": self.default_model_url,
                                "garment_image_urls": product_images[:3]
                            }
                        )
                        response.raise_for_status()
                        result = response.json()
                        
                        if result.get("output_image_url"):
                            return result["output_image_url"]
                except Exception as e:
                    logger.warning(f"Error using try-on API for default model: {e}")
        
        # Fallback 1: возвращаем URL типовой модели из legacy-файла
        default_model_path = Path("static") / "default_glame_model.jpg"
        if default_model_path.exists():
            logger.info(f"Using default GLAME model: {self.default_model_url}")
            return self.default_model_url

        # Fallback 2: если legacy-файла нет, берем первое фото из цифровых моделей static/models
        model_refs = self._discover_model_reference_images(model_profile=None, limit=1)
        if model_refs:
            logger.info("Legacy default model not found, using first digital model source image: %s", model_refs[0])
            return model_refs[0]

        logger.warning(f"Default model image not found at {default_model_path}, and no digital model source images available.")
        return None
    
    async def generate_look_image_from_look(
        self,
        look_id: UUID,
        use_default_model: bool = False,
        digital_model: Optional[str] = None,
    ) -> Optional[str]:
        """
        Генерация изображения для существующего образа
        
        Args:
            look_id: ID образа
            use_default_model: Использовать типовую модель
        
        Returns:
            URL изображения
        """
        from sqlalchemy import select
        from app.models.look import Look
        from app.models.product import Product
        from app.database.connection import AsyncSessionLocal
        
        # Используем переданную сессию, если она есть, иначе создаем новую
        db = self.db
        should_close_db = False
        
        if not db:
            db = AsyncSessionLocal()
            should_close_db = True
        
        try:
            # Получаем образ
            result = await db.execute(select(Look).where(Look.id == look_id))
            look = result.scalar_one_or_none()
            
            if not look:
                logger.error(f"Look {look_id} not found")
                return None
            
            # Получаем товары
            product_ids = [UUID(pid) for pid in (look.product_ids or [])]
            products = []
            if product_ids:
                try:
                    products_result = await db.execute(
                        select(Product).where(Product.id.in_(product_ids))
                    )
                    products = products_result.scalars().all()
                except Exception as e:
                    logger.error(f"Error loading products for look {look_id}: {e}")
                    products = []
            
            # Формируем описание
            look_description = {
                "name": look.name or "Образ",
                "description": look.description or "",
                "style": look.style or "",
                "mood": look.mood or ""
            }
            metadata = look.generation_metadata or {}
            selected_model = self._sanitize_profile_name(digital_model or metadata.get("digital_model"))
            
            # Формируем список товаров с изображениями
            products_list = []
            for p in products:
                product_dict = {
                    "name": p.name or "",
                    "description": p.description or "",
                    "category": p.category or "",
                    "images": []
                }
                # Обрабатываем изображения товаров
                if p.images:
                    if isinstance(p.images, list):
                        product_dict["images"] = p.images
                    elif isinstance(p.images, str):
                        product_dict["images"] = [p.images]
                
                products_list.append(product_dict)
            
            logger.info(f"Generating image for look {look_id} with {len(products_list)} products")
            
            # Генерируем изображение (используем переданную сессию через self.db)
            # Временно сохраняем текущую сессию
            original_db = self.db
            self.db = db
            
            try:
                image_url = await self.generate_look_image(
                    look_description=look_description,
                    products=products_list,
                    use_default_model=use_default_model,
                    model_profile=selected_model,
                    asset_group=f"look_images/models/{selected_model}" if selected_model else "look_images",
                    filename_prefix=f"look_{selected_model}" if selected_model else "look",
                )
                return image_url
            finally:
                # Восстанавливаем оригинальную сессию
                self.db = original_db
                
        except Exception as e:
            logger.exception(f"Error generating image for look {look_id}: {e}")
            return None
        finally:
            # Закрываем сессию только если мы её создали
            if should_close_db and db:
                await db.close()


# Глобальный экземпляр сервиса
image_generation_service = ImageGenerationService()
