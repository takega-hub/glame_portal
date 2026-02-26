import os
import httpx
from typing import Optional, List, Dict
from dotenv import load_dotenv, find_dotenv

# Важно: при запуске из разных директорий (Windows/venv/IDE) load_dotenv() без usecwd=True
# может не найти корневой .env. Поэтому используем find_dotenv(usecwd=True).
load_dotenv(find_dotenv(usecwd=True), override=False)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "anthropic/claude-3.5-sonnet")


class LLMService:
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.default_model = DEFAULT_MODEL

    async def _get_default_model_from_settings(self) -> Optional[str]:
        """
        Пытаемся получить default_model из БД (app_settings), иначе возвращаем None.
        Не должен валить генерацию, если БД недоступна.
        """
        try:
            from sqlalchemy import select
            from app.database.connection import AsyncSessionLocal
            from app.models.app_setting import AppSetting

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(AppSetting).where(AppSetting.key == "default_model"))
                setting = result.scalar_one_or_none()
                if setting and setting.value:
                    return str(setting.value).strip()
        except Exception:
            return None
        return None
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        Генерация текста через OpenRouter API
        """
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY не установлен. "
                "Установите переменную окружения OPENROUTER_API_KEY в файле .env или в системе."
            )
        
        if model:
            chosen_model = model
        else:
            chosen_model = await self._get_default_model_from_settings()
            if not chosen_model:
                chosen_model = self.default_model
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://glame.ai",
                    "X-Title": "GLAME AI Platform",
                },
                json={
                    "model": chosen_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs
                },
                timeout=300.0  # Увеличено до 5 минут для генерации больших планов
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
    
    async def generate_structured(
        self,
        prompt: str,
        response_format: Dict,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """
        Генерация структурированного ответа (JSON)
        """
        import json
        
        system = system_prompt or ""
        system += "\n\nОтвечай ТОЛЬКО валидным JSON без дополнительного текста."
        
        full_prompt = f"{prompt}\n\nФормат ответа: {json.dumps(response_format, ensure_ascii=False, indent=2)}"
        
        raw_content = await self.generate(
            prompt=full_prompt,
            model=model,
            system_prompt=system,
            **kwargs
        )
        # OpenRouter может вернуть None или список content blocks
        if raw_content is None:
            return {"raw_response": "", "parse_error": "Пустой ответ от модели"}
        if not isinstance(raw_content, str):
            if isinstance(raw_content, list):
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                raw_content = "\n".join(text_parts)
            else:
                raw_content = str(raw_content)

        response = raw_content.strip()
        if not response:
            return {"raw_response": "", "parse_error": "Пустой текст в ответе модели"}

        # Удаляем markdown код блоки если есть
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        response = response.strip()

        # Попытка распарсить JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Пробуем извлечь JSON объект по первой { и последней }
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(response[start : end + 1])
                except json.JSONDecodeError:
                    pass
            return {"raw_response": raw_content[:2000], "parse_error": "Не удалось распознать JSON в ответе"}


# Singleton instance
llm_service = LLMService()
