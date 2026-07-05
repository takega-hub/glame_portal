import os
import httpx
from typing import Optional, List, Dict
from dotenv import load_dotenv, find_dotenv

# Важно: при запуске из разных директорий (Windows/venv/IDE) load_dotenv() без usecwd=True
# может не найти корневой .env. Поэтому используем find_dotenv(usecwd=True).
load_dotenv(find_dotenv(usecwd=True), override=False)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openrouter/auto")

LEGACY_MODEL_ALIASES = {
    "anthropic/claude-3.5-sonnet": "openrouter/auto",
}

FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv("OPENROUTER_FALLBACK_MODELS", "openrouter/auto,openai/gpt-4o-mini").split(",")
    if model.strip()
]


class LLMService:
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.default_model = DEFAULT_MODEL
        self.cost_log_path = os.getenv("OPENROUTER_COST_LOG_PATH", "/tmp/openrouter_costs.jsonl")

    @staticmethod
    def _normalize_model(model: Optional[str]) -> Optional[str]:
        if not model:
            return None
        normalized = str(model).strip()
        return LEGACY_MODEL_ALIASES.get(normalized, normalized)

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
            chosen_model = self._normalize_model(model)
        else:
            chosen_model = self._normalize_model(await self._get_default_model_from_settings())
            if not chosen_model:
                chosen_model = self._normalize_model(self.default_model)
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        candidate_models = [chosen_model]
        for fallback_model in FALLBACK_MODELS:
            normalized_fallback = self._normalize_model(fallback_model)
            if normalized_fallback and normalized_fallback not in candidate_models:
                candidate_models.append(normalized_fallback)

        async with httpx.AsyncClient() as client:
            result = None
            used_model = chosen_model
            last_error: Optional[Exception] = None
            for candidate_model in candidate_models:
                used_model = candidate_model
                payload = {
                    "model": candidate_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                }
                if candidate_model == "openrouter/auto":
                    payload.pop("provider", None)
                    payload.pop("models", None)

                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "HTTP-Referer": "https://glame.ai",
                            "X-Title": "GLAME AI Platform",
                        },
                        json=payload,
                        timeout=300.0  # Увеличено до 5 минут для генерации больших планов
                    )
                    response.raise_for_status()
                    result = response.json()
                    break
                except httpx.HTTPStatusError as e:
                    try:
                        detail = e.response.text
                    except Exception:
                        detail = str(e)
                    last_error = ValueError(f"OpenRouter chat/completions {e.response.status_code}: {detail}")
                    retryable = (
                        e.response.status_code in {400, 404, 429, 500, 502, 503, 504}
                        and any(
                            marker in detail.lower()
                            for marker in [
                                "no endpoints",
                                "unknown model",
                                "not a valid model",
                                "no allowed providers",
                                "rate limit",
                            ]
                        )
                    )
                    if not retryable or candidate_model == candidate_models[-1]:
                        raise last_error from e
                    continue

            if result is None:
                raise last_error or ValueError("OpenRouter returned no response")
            try:
                usage = result.get("usage") or {}
                if usage:
                    import json, time
                    os.makedirs(os.path.dirname(self.cost_log_path), exist_ok=True)
                    rec = {
                        "ts": time.time(),
                        "model": used_model,
                        "requested_model": chosen_model,
                        "cost": float(usage.get("cost") or 0),
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "source": "chat.completions",
                    }
                    with open(self.cost_log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass
            content = (
                ((result.get("choices") or [{}])[0].get("message") or {}).get("content")
                if isinstance(result, dict)
                else None
            )
            return content if isinstance(content, str) else ""
    
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
