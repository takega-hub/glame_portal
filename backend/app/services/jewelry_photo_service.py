"""
Сервис ретуши фото украшений для каталога GLAME.

По умолчанию обработка выполняется через Hermes runtime и GPT Image 2.
Legacy OpenRouter оставлен только для явного аварийного режима.
"""
import asyncio
import json
import os
import re
import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

# Основной формат GLAME из утвержденного ретушь-промпта: вертикальный 3:4.
OUTPUT_WIDTH = 1536
OUTPUT_HEIGHT = 2048
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

JEWELRY_PROCESSING_PROMPT = """Обработай предметное фото украшения GLAME в эстетике Net-a-Porter / Farfetch luxury jewelry catalog / Vogue Jewelry / Tiffany clean product photography.

Сохрани реальное изделие: не меняй форму, толщину, пропорции, геометрию, конструкцию, посадку, ракурс, камни, жемчуг, замки и реальные особенности украшения. Это должна быть ретушь исходного фото, а не генерация нового изделия и не CGI.

Сделай чистый белый или холодно-белый фон без бумаги, пятен, стола, рук, телефона, лишних объектов и грязных серых зон. Изделие строго по центру, с большим количеством воздуха вокруг. Масштаб реалистичный, без чрезмерного увеличения.

Свет мягкий студийный, премиальный, с аккуратными контролируемыми бликами. Тень короткая, мягкая, чистая, контактная, без грязного ореола.

Металл сделай дорогим и реалистичным: если золото — нейтральное luxury gold без оранжевости, кислотной желтизны и зеленцы; если серебро — холодное, чистое, полированное, не серое, не белесое и не пластиковое. Убери отражения телефона, рук, комнаты и грязные пятна, но сохрани живой объем металла.

Если есть жемчуг — сделай его натуральным, перламутровым, мягким и объемным, без пластика и мыльности. Если есть камни/Swarovski — добавь аккуратную четкость и премиальный блеск без дешевого glitter-эффекта.

Финальный формат: 1536 × 2048 px, вертикальный 3:4. Без текста, логотипов, интерфейса и декоративных элементов."""

JEWELRY_REVISION_PROMPT = """Доведи фото до уровня Net-a-Porter luxury jewelry product shot. Сохрани реальную форму и конструкцию изделия, не перерисовывай. Убери ощущение CGI/рендера. Сделай металл чище, дороже и реалистичнее, фон холодно-белым и чистым, тень мягкой и короткой. Добавь четкости без перешарпа. Не меняй пропорции, ракурс, толщину, геометрию, камни/жемчуг и посадку элементов."""

HERMES_CODEX_IMAGE_SCRIPT = r"""
import base64
import json
import sys

import httpx

from agent.auxiliary_client import _codex_cloudflare_headers, _read_codex_access_token

CODEX_CHAT_MODEL = "gpt-5.4"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


def _extract_image_b64(value):
    found = None
    if isinstance(value, dict):
        if value.get("type") == "image_generation_call":
            result = value.get("result")
            if isinstance(result, str) and result:
                found = result
        partial = value.get("partial_image_b64")
        if isinstance(partial, str) and partial:
            found = partial
        for child in value.values():
            nested = _extract_image_b64(child)
            if nested:
                found = nested
    elif isinstance(value, list):
        for child in value:
            nested = _extract_image_b64(child)
            if nested:
                found = nested
    return found


def _iter_sse_json(response):
    event_name = None
    data_lines = []

    def flush():
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = None
            return None
        raw = "\n".join(data_lines).strip()
        event = event_name
        event_name = None
        data_lines = []
        if not raw or raw == "[DONE]":
            return None
        payload = json.loads(raw)
        if isinstance(payload, dict) and event and "type" not in payload:
            payload["type"] = event
        return payload

    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = str(line)
        if line == "":
            payload = flush()
            if payload is not None:
                yield payload
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())

    payload = flush()
    if payload is not None:
        yield payload


def main():
    payload_in = json.load(sys.stdin)
    prompt = payload_in["prompt"]
    mime = payload_in["mime"]
    image_b64 = payload_in["image_b64"]
    quality = payload_in.get("quality") or "medium"
    size = payload_in.get("size") or "1024x1536"

    token = _read_codex_access_token()
    if not token:
        raise RuntimeError("Hermes Codex auth is not configured. Run `hermes auth codex`.")

    headers = _codex_cloudflare_headers(token)
    headers.update({
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })

    request = {
        "model": CODEX_CHAT_MODEL,
        "store": False,
        "instructions": (
            "You are the GLAME jewelry retouching agent. Use the provided source image "
            "as the strict visual reference and fulfill the request through the image_generation tool."
        ),
        "input": [{
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:{mime};base64,{image_b64}"},
            ],
        }],
        "tools": [{
            "type": "image_generation",
            "model": "gpt-image-2",
            "size": size,
            "quality": quality,
            "output_format": "png",
            "background": "opaque",
            "partial_images": 1,
        }],
        "tool_choice": {
            "type": "allowed_tools",
            "mode": "required",
            "tools": [{"type": "image_generation"}],
        },
        "stream": True,
    }

    timeout = httpx.Timeout(300.0, connect=30.0, read=300.0, write=30.0, pool=30.0)
    image_out = None
    with httpx.Client(timeout=timeout, headers=headers) as client:
        with client.stream("POST", f"{CODEX_BASE_URL}/responses", json=request) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                exc.response.read()
                raise RuntimeError(
                    f"Hermes GPT Image 2 returned HTTP {exc.response.status_code}: {exc.response.text[:800]}"
                ) from exc
            for event in _iter_sse_json(response):
                found = _extract_image_b64(event)
                if found:
                    image_out = found

    if not image_out:
        raise RuntimeError("Hermes GPT Image 2 returned no image.")

    print(json.dumps({"success": True, "image_b64": image_out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
"""


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
        self.runtime = (os.getenv("JEWELRY_PHOTO_RUNTIME") or os.getenv("GLAME_IMAGE_RUNTIME") or "hermes").strip().lower()
        self.hermes_home = Path(os.getenv("HERMES_AGENT_HOME", "/home/glameAI/hermes-agent"))
        self.hermes_python = os.getenv(
            "HERMES_PYTHON",
            str(self.hermes_home / "venv" / "bin" / "python"),
        )
        self.hermes_model = os.getenv("JEWELRY_PHOTO_HERMES_MODEL", "gpt-image-2").strip() or "gpt-image-2"
        self.hermes_quality = os.getenv("JEWELRY_PHOTO_HERMES_QUALITY", "medium").strip() or "medium"
        self.storage_dir = Path("static/jewelry_processed")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.last_prompt_used: Optional[str] = None

    def build_prompt(
        self,
        revision_description: Optional[str] = None,
        prompt_override: Optional[str] = None,
    ) -> str:
        """Формирует финальный промпт, который реально уйдет в image model."""
        base_prompt = (prompt_override or "").strip() or JEWELRY_PROCESSING_PROMPT
        if len(base_prompt) > 8000:
            raise JewelryPhotoServiceError("Промпт слишком длинный: максимум 8000 символов.")
        revision = (revision_description or "").strip()
        if not revision:
            return base_prompt
        if (prompt_override or "").strip():
            return f"{base_prompt}\n\nДополнительное пожелание пользователя (учти при обработке): {revision}"
        return (
            f"{JEWELRY_REVISION_PROMPT}\n\n"
            f"Дополнительное пожелание пользователя: {revision}\n\n"
            f"Полные правила GLAME для контроля качества:\n{JEWELRY_PROCESSING_PROMPT}"
        )

    def provider_info(self) -> dict:
        if self.runtime == "openrouter":
            return {"runtime": "openrouter", "model": os.getenv("IMAGE_GENERATION_MODEL") or "settings:image_generation_model"}
        return {
            "runtime": "hermes",
            "model": self.hermes_model,
            "profile": "glame-jewelry-retoucher",
            "quality": self.hermes_quality,
        }

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
        prompt_override: Optional[str] = None,
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

        prompt = self.build_prompt(revision_description=revision_description, prompt_override=prompt_override)
        self.last_prompt_used = prompt
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

    async def _process_one_with_hermes_gpt_image_2(
        self,
        image_bytes: bytes,
        revision_description: Optional[str] = None,
        prompt_override: Optional[str] = None,
    ) -> bytes:
        """Ретуширует фото через Hermes Codex-auth provider и GPT Image 2."""
        hermes_python = Path(self.hermes_python)
        if not hermes_python.is_file():
            raise JewelryPhotoServiceError(
                f"Hermes Python runtime не найден: {hermes_python}. Проверьте HERMES_PYTHON."
            )
        if not self.hermes_home.is_dir():
            raise JewelryPhotoServiceError(
                f"Hermes agent home не найден: {self.hermes_home}. Проверьте HERMES_AGENT_HOME."
            )

        fmt = "png" if image_bytes[:8].startswith(b"\x89PNG") else "jpeg"
        mime = "image/png" if fmt == "png" else "image/jpeg"
        prompt = self.build_prompt(revision_description=revision_description, prompt_override=prompt_override)
        self.last_prompt_used = prompt

        request_payload = {
            "prompt": prompt,
            "mime": mime,
            "image_b64": base64.b64encode(image_bytes).decode("utf-8"),
            "quality": self.hermes_quality,
            "size": "1024x1536",
        }

        env = os.environ.copy()
        env.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
        env["PYTHONPATH"] = str(self.hermes_home)

        try:
            proc = await asyncio.create_subprocess_exec(
                str(hermes_python),
                "-c",
                HERMES_CODEX_IMAGE_SCRIPT,
                cwd=str(self.hermes_home),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(json.dumps(request_payload).encode("utf-8")),
                timeout=330.0,
            )
        except asyncio.TimeoutError as exc:
            raise JewelryPhotoServiceError("Hermes GPT Image 2 не успел обработать фото за 5 минут.") from exc
        except Exception as exc:
            raise JewelryPhotoServiceError(f"Не удалось запустить Hermes GPT Image 2: {exc}") from exc

        if proc.returncode != 0:
            detail = (stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace")).strip()
            raise JewelryPhotoServiceError(f"Hermes GPT Image 2 error: {detail[:1200]}")

        try:
            data = json.loads(stdout.decode("utf-8"))
            image_b64 = data.get("image_b64")
            if not image_b64:
                raise ValueError("image_b64 is empty")
            return base64.b64decode(image_b64)
        except Exception as exc:
            logger.warning("Could not parse Hermes image response: %s; stdout=%s", exc, stdout[:500])
            raise JewelryPhotoServiceError("Hermes GPT Image 2 вернул некорректный результат.") from exc

    def _postprocess_with_pillow(self, image_bytes: bytes) -> bytes:
        """Наложение на белый фон, вертикальный 3:4, лёгкое усиление резкости/контраста."""
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
        canvas_ratio = OUTPUT_WIDTH / OUTPUT_HEIGHT
        img_ratio = w / h if h else 1
        if img_ratio > canvas_ratio:
            paste_w = OUTPUT_WIDTH
            paste_h = max(1, int(OUTPUT_WIDTH / img_ratio))
        else:
            paste_h = OUTPUT_HEIGHT
            paste_w = max(1, int(OUTPUT_HEIGHT * img_ratio))

        img = img.resize((paste_w, paste_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (OUTPUT_WIDTH, OUTPUT_HEIGHT), (255, 255, 255, 255))
        paste_x = (OUTPUT_WIDTH - paste_w) // 2
        paste_y = (OUTPUT_HEIGHT - paste_h) // 2
        canvas.paste(img, (paste_x, paste_y), img if img.mode == "RGBA" else None)
        canvas_rgb = Image.new("RGB", canvas.size, (255, 255, 255))
        canvas_rgb.paste(canvas, mask=canvas.split()[3] if canvas.mode == "RGBA" else None)
        out = canvas_rgb

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
        prompt_override: Optional[str] = None,
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
        # Валидируем и фиксируем финальный промпт до запуска, чтобы его можно было вернуть в UI.
        self.last_prompt_used = self.build_prompt(
            revision_description=revision_description,
            prompt_override=prompt_override,
        )
        for i, b in enumerate(image_bytes_list):
            if len(b) > MAX_FILE_BYTES:
                raise JewelryPhotoServiceError(
                    f"Файл {i + 1} превышает лимит 10 MB."
                )

        model = await self._get_model_from_settings()
        if not model:
            model = os.getenv("IMAGE_GENERATION_MODEL", "black-forest-labs/flux-pro")
        logger.info(
            "Jewelry photo processing: runtime=%s, hermes_model=%s, legacy_model=%s, images=%s, article=%s",
            self.runtime,
            self.hermes_model,
            model,
            len(image_bytes_list),
            article,
        )

        sanitized = _sanitize_article(article)
        urls = []

        for idx, img_bytes in enumerate(image_bytes_list):
            try:
                logger.info("Processing image %s/%s...", idx + 1, len(image_bytes_list))
                if self.runtime == "openrouter":
                    processed = await self._process_one_with_openrouter(
                        img_bytes,
                        model,
                        revision_description=revision_description,
                        prompt_override=prompt_override,
                    )
                else:
                    processed = await self._process_one_with_hermes_gpt_image_2(
                        img_bytes,
                        revision_description=revision_description,
                        prompt_override=prompt_override,
                    )
                logger.info("Model returned image, size=%s bytes", len(processed))
            except ModelDoesNotSupportImageError:
                raise
            except Exception as e:
                logger.exception("Jewelry photo processing failed for image %s: %s", idx, e)
                raise JewelryPhotoServiceError(
                    f"Ошибка обработки изображения: {str(e)}. "
                    "Проверьте Hermes/Codex авторизацию и доступность GPT Image 2."
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
