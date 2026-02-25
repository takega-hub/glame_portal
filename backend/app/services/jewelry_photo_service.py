"""
Сервис обработки фото украшений для каталога: удаление фона, белый фон, единый стиль.
Модель берётся из настроек (image_generation_model). Обработанные изображения
сохраняются по имени артикула и используются для генерации образов.
"""
import os
import re
import base64
import logging
from pathlib import Path
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

# Размер выходного квадратного изображения (пиксели)
OUTPUT_SIZE = 1024
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

JEWELRY_PROCESSING_PROMPT = """Обработай это фото украшения для каталога e-commerce:
- Удали весь фон, замени на чистый белый (#FFFFFF).
- Оставь только украшение в центре, без лишних элементов (пальцы, подставки, пыль).
- Идеальное студийное освещение: мягкий свет спереди, лёгкие блики на металле/камнях.
- Крупный план, украшение занимает большую часть кадра.
- Вывод: одно чистое PNG-фото на белом фоне для каталога (professional jewelry product shot)."""


def _sanitize_article(article: str) -> str:
    """Заменяет недопустимые для файловой системы символы в артикуле."""
    if not article or not article.strip():
        return "product"
    s = article.strip()
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:100] or "product"


class JewelryPhotoServiceError(Exception):
    """Ошибка сервиса обработки фото украшений."""
    pass


class ModelDoesNotSupportImageError(JewelryPhotoServiceError):
    """Выбранная модель не поддерживает ввод изображения."""
    pass


class JewelryPhotoService:
    """Обработка фото украшений: модель из настроек + постобработка Pillow."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.api_key = os.getenv("IMAGE_GENERATION_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        self.api_url = os.getenv("IMAGE_GENERATION_API_URL", "https://openrouter.ai/api/v1")
        self.storage_dir = Path("static/jewelry_processed")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def _get_model_from_settings(self) -> Optional[str]:
        """Получает модель для обработки изображений из БД (тот же ключ, что и для генерации)."""
        db = self.db
        if not db:
            async with AsyncSessionLocal() as session:
                return await self._get_model_from_session(session)
        return await self._get_model_from_session(db)

    @staticmethod
    async def _get_model_from_session(session: AsyncSession) -> Optional[str]:
        try:
            result = await session.execute(
                select(AppSetting).where(AppSetting.key == "image_generation_model")
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return str(setting.value).strip()
        except Exception as e:
            logger.warning(f"Could not get image_generation_model from settings: {e}")
        return None

    async def _process_one_with_openrouter(
        self,
        image_bytes: bytes,
        model: str,
        revision_description: Optional[str] = None,
    ) -> bytes:
        """
        Отправляет одно изображение в OpenRouter с промптом обработки.
        Возвращает байты результата. При ошибке (модель не поддерживает image input) бросает исключение.
        """
        if not self.api_key:
            raise JewelryPhotoServiceError("Не задан OPENROUTER_API_KEY или IMAGE_GENERATION_API_KEY")

        # Определяем MIME по заголовкам или расширению не применимо — у нас байты; пробуем как PNG, иначе JPEG
        fmt = "png" if image_bytes[:8].startswith(b"\x89PNG") else "jpeg"
        mime = "image/png" if fmt == "png" else "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = JEWELRY_PROCESSING_PROMPT
        if revision_description and revision_description.strip():
            prompt = prompt.rstrip() + "\n\nДополнительное пожелание пользователя (учти при обработке): " + revision_description.strip()
        messages_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            },
            {"type": "text", "text": prompt},
        ]

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": messages_content}],
            "modalities": ["image", "text"],
        }
        model_lower = model.lower()
        if "gemini" in model_lower:
            payload["image_config"] = {"aspect_ratio": "1:1", "image_size": "4K"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://glame.ai",
                    "X-Title": "GLAME AI Platform",
                },
                json=payload,
            )

            if response.status_code == 400 or response.status_code == 422:
                text = (response.text or "")[:500]
                if "image" in text.lower() or "modality" in text.lower() or "input" in text.lower():
                    raise ModelDoesNotSupportImageError(
                        "Выбранная модель не поддерживает обработку изображений. "
                        "Выберите в Настройках модель с поддержкой image input (например Gemini с изображением)."
                    )
                raise JewelryPhotoServiceError(f"Ошибка API: {text}")

            response.raise_for_status()
            result = response.json()

        logger.info("OpenRouter response received, parsing image...")
        choices = result.get("choices", [])
        if not choices:
            raise JewelryPhotoServiceError("В ответе API нет результата (choices пуст).")
        message = choices[0].get("message", {})
        image_data = None

        # Формат 1: message.images[0].image_url.url (OpenRouter image generation)
        images = message.get("images", [])
        if images and len(images) > 0:
            first = images[0]
            if isinstance(first, dict):
                img_url_obj = first.get("image_url")
                if isinstance(img_url_obj, dict):
                    image_data = img_url_obj.get("url", "")
                else:
                    image_data = first.get("url", first.get("image_url") or "")
            elif isinstance(first, str):
                image_data = first
            else:
                image_data = ""

        # Формат 2: message.content — массив частей, среди которых type image_url
        if not image_data and isinstance(message.get("content"), list):
            for part in message["content"]:
                if isinstance(part, dict):
                    if part.get("type") == "image_url":
                        img_url_part = part.get("image_url")
                        if isinstance(img_url_part, dict):
                            image_data = img_url_part.get("url")
                        elif isinstance(img_url_part, str):
                            image_data = img_url_part
                        if image_data:
                            break
                    if part.get("type") == "image" and part.get("image"):
                        img = part["image"]
                        if isinstance(img, str):
                            return base64.b64decode(img)
                        if isinstance(img, bytes):
                            return img

        if not image_data:
            logger.warning("No image in response; message keys: %s", list(message.keys()))
            raise ModelDoesNotSupportImageError(
                "Выбранная модель не поддерживает обработку изображений. "
                "Выберите в Настройках модель с поддержкой image input (например Gemini с изображением)."
            )
        image_data = str(image_data).strip()
        logger.info("Image data extracted from response (data:image=%s, http=%s)", image_data.startswith("data:image"), image_data.startswith("http"))

        if image_data.startswith("data:image"):
            base64_data = image_data.split(",", 1)[1]
            return base64.b64decode(base64_data)
        if image_data.startswith("http"):
            async with httpx.AsyncClient(timeout=60.0) as client:
                img_resp = await client.get(image_data)
                img_resp.raise_for_status()
                return img_resp.content
        try:
            decoded = base64.b64decode(image_data)
            logger.info("Image decoded from base64, size=%s bytes", len(decoded))
            return decoded
        except Exception as e:
            logger.warning("Failed to decode image data: %s", e)
            raise JewelryPhotoServiceError("Не удалось извлечь изображение из ответа API.")

    def _postprocess_with_pillow(self, image_bytes: bytes) -> bytes:
        """Наложение на белый фон, квадрат, лёгкое усиление резкости/контраста/насыщенности."""
        try:
            from PIL import Image, ImageEnhance
            import io
        except ImportError as e:
            logger.warning(f"Pillow not available: {e}, skipping postprocess")
            return image_bytes

        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        except Exception as e:
            logger.warning(f"Pillow could not open image (maybe not an image): {e}, returning raw bytes")
            return image_bytes

        w, h = img.size
        size = max(w, h, OUTPUT_SIZE)
        canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        paste_x = (size - w) // 2
        paste_y = (size - h) // 2
        canvas.paste(img, (paste_x, paste_y), img if img.mode == "RGBA" else None)
        canvas_rgb = Image.new("RGB", canvas.size, (255, 255, 255))
        canvas_rgb.paste(canvas, mask=canvas.split()[3] if canvas.mode == "RGBA" else None)
        out = canvas_rgb.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.Resampling.LANCZOS)

        try:
            enhancer = ImageEnhance.Sharpness(out)
            out = enhancer.enhance(1.2)
            enhancer = ImageEnhance.Contrast(out)
            out = enhancer.enhance(1.1)
            enhancer = ImageEnhance.Color(out)
            out = enhancer.enhance(1.1)
        except Exception as e:
            logger.warning(f"Pillow enhance failed: {e}")

        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _get_available_filename(self, desired_filename: str) -> str:
        """Если файл с таким именем уже есть — возвращает имя с индексом (article_1.png, article_2.png, ...)."""
        path = self.storage_dir / desired_filename
        if not path.exists():
            return desired_filename
        stem = path.stem
        suffix = path.suffix
        for i in range(1, 1000):
            candidate = f"{stem}_{i}{suffix}"
            if not (self.storage_dir / candidate).exists():
                logger.info("File %s exists, using %s", desired_filename, candidate)
                return candidate
        raise JewelryPhotoServiceError("Не удалось подобрать свободное имя файла (слишком много вариантов).")

    def _save_and_get_url(self, png_bytes: bytes, filename: str) -> str:
        """Сохраняет PNG в static/jewelry_processed. Если имя занято — используется имя с индексом."""
        actual_filename = self._get_available_filename(filename)
        path = self.storage_dir / actual_filename
        path.write_bytes(png_bytes)
        return f"/static/jewelry_processed/{actual_filename}"

    async def process_batch(
        self,
        image_bytes_list: List[bytes],
        article: str,
        revision_description: Optional[str] = None,
    ) -> List[str]:
        """
        Обрабатывает список фото украшений с одинаковыми параметрами.
        revision_description — описание доработок при перегенерации (добавляется к промпту).
        Имена файлов: {article}.png или {article}_0.png, {article}_1.png, ...
        Возвращает список относительных URL в том же порядке.
        """
        if not image_bytes_list:
            return []
        if len(image_bytes_list) > MAX_FILES:
            raise JewelryPhotoServiceError(f"Максимум {MAX_FILES} фото за один запрос.")
        for i, b in enumerate(image_bytes_list):
            if len(b) > MAX_FILE_BYTES:
                raise JewelryPhotoServiceError(
                    f"Файл {i + 1} превышает лимит 10 MB."
                )

        model = await self._get_model_from_settings()
        if not model:
            model = os.getenv("IMAGE_GENERATION_MODEL", "black-forest-labs/flux-pro")
        logger.info(f"Jewelry photo processing: model={model}, images={len(image_bytes_list)}, article={article}")

        sanitized = _sanitize_article(article)
        urls = []

        for idx, img_bytes in enumerate(image_bytes_list):
            try:
                logger.info("Processing image %s/%s...", idx + 1, len(image_bytes_list))
                processed = await self._process_one_with_openrouter(
                    img_bytes, model, revision_description=revision_description
                )
                logger.info("Model returned image, size=%s bytes", len(processed))
            except ModelDoesNotSupportImageError:
                raise
            except Exception as e:
                logger.exception(f"OpenRouter processing failed for image {idx}: {e}")
                raise JewelryPhotoServiceError(
                    f"Ошибка обработки изображения: {str(e)}. "
                    "Убедитесь, что выбранная модель поддерживает ввод изображения (Настройки)."
                )

            # 2) Постобработка Pillow
            final_bytes = self._postprocess_with_pillow(processed)
            logger.info("Postprocess done, saving image %s/%s", idx + 1, len(image_bytes_list))

            # 3) Имя файла: артикул или артикул_0, артикул_1, ...
            if len(image_bytes_list) == 1:
                filename = f"{sanitized}.png"
            else:
                filename = f"{sanitized}_{idx}.png"

            url = self._save_and_get_url(final_bytes, filename)
            urls.append(url)

        return urls

    def list_history(self) -> List[dict]:
        """
        Сканирует папку сохранённых фото, группирует по артикулу.
        Возвращает список: [ { "article": str, "urls": [str], "updated_at": str ISO }, ... ],
        отсортированный по updated_at по убыванию.
        """
        if not self.storage_dir.exists():
            return []
        groups: dict = {}
        for path in self.storage_dir.iterdir():
            if path.is_file() and path.suffix.lower() == ".png":
                # Артикул: U10046.png -> U10046; U10046_1.png -> U10046
                stem = path.stem
                if "_" in stem and stem.split("_")[-1].isdigit():
                    article = stem.rsplit("_", 1)[0]
                else:
                    article = stem
                url = f"/static/jewelry_processed/{path.name}"
                mtime = path.stat().st_mtime
                if article not in groups:
                    groups[article] = {"urls": [], "updated_at": mtime}
                groups[article]["urls"].append(url)
                groups[article]["updated_at"] = max(groups[article]["updated_at"], mtime)
        from datetime import datetime, timezone
        out = [
            {
                "article": art,
                "urls": sorted(data["urls"]),
                "updated_at": datetime.fromtimestamp(data["updated_at"], tz=timezone.utc).isoformat(),
            }
            for art, data in groups.items()
        ]
        out.sort(key=lambda x: x["updated_at"], reverse=True)
        return out

    def delete_file_by_url(self, url: str) -> bool:
        """
        Удаляет файл по относительному URL (например /static/jewelry_processed/U10046_1.png).
        Возвращает True если файл удалён, False если не найден. Бросает при попытке выйти из папки.
        """
        if not url or not url.strip().startswith("/static/jewelry_processed/"):
            raise JewelryPhotoServiceError("Недопустимый URL файла.")
        name = url.strip().removeprefix("/static/jewelry_processed/").strip()
        if ".." in name or "/" in name or "\\" in name:
            raise JewelryPhotoServiceError("Недопустимое имя файла.")
        path = self.storage_dir / name
        if not path.is_file():
            return False
        path.unlink()
        logger.info("Deleted jewelry processed file: %s", path.name)
        return True
