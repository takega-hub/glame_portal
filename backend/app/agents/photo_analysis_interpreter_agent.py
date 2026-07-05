import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_system_prompt import AgentSystemPrompt
from app.services.llm_service import llm_service


logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


class PhotoAnalysisInterpreterAgent:
    AGENT_TYPE = "photo-analysis-interpreter"
    SYSTEM_PROMPT = """Ты - AI-стилист GLAME, который объясняет результаты уже готового технического анализа фото.

Твоя задача:
1. Превратить структурированный анализ внешности в человеческое описание.
2. Коротко описать внешность, лицо, типаж и цветовое впечатление.
3. Объяснять мягко, уважительно и профессионально.

Строгие правила:
- Опирайся только на входной structured analysis.
- Не выдумывай признаки, которых нет во входных данных.
- Не делай выводов о возрасте, этничности, здоровье, характере, социальном статусе, привлекательности.
- Не используй медицинские формулировки и не оценивай внешность.
- Не упоминай названия внутренних полей JSON.
- Пиши так, как стилист объяснил бы клиенту результат разбора внешности.
- Если данных мало, формулируй осторожно: "считывается как", "выглядит более", "лучше поддержать".

Верни только JSON.
"""
    RESPONSE_FORMAT = {
        "summary": "Короткое человеческое описание внешности в 2-4 предложениях.",
        "appearance": "Описание общего визуального впечатления и типажа.",
        "face": "Описание формы лица, линий, масштаба черт и акцентных зон.",
        "style_type": "Короткое название стилевого типа, 2-5 слов.",
        "color_type": "Короткое название цветового впечатления, 2-5 слов.",
        "bullets": [
            "Ключевая мысль 1",
            "Ключевая мысль 2",
            "Ключевая мысль 3",
        ],
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = llm_service

    async def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return await self.describe(input_data)

    async def describe(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        if analysis_payload.get("can_continue") is not True:
            return self._retry_payload(analysis_payload)

        system_prompt = await self.get_active_system_prompt(
            self.AGENT_TYPE,
            self.SYSTEM_PROMPT,
        )
        prompt = self._build_prompt(analysis_payload)

        try:
            structured = await self.llm.generate_structured(
                prompt=prompt,
                response_format=self.RESPONSE_FORMAT,
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=1200,
            )
            normalized = self._normalize_response(structured)
            if normalized:
                normalized = self._enrich_with_eye_color(normalized, analysis_payload)
                normalized["source"] = "llm"
                normalized["agent_type"] = self.AGENT_TYPE
                return normalized
        except Exception as exc:
            logger.warning("PhotoAnalysisInterpreterAgent fallback after LLM error: %s", exc)

        fallback = self._fallback_from_analysis(analysis_payload)
        fallback = self._enrich_with_eye_color(fallback, analysis_payload)
        fallback["source"] = "fallback"
        fallback["agent_type"] = self.AGENT_TYPE
        return fallback

    async def get_active_system_prompt(
        self,
        agent_type: str,
        fallback_prompt: str,
    ) -> str:
        try:
            query = select(AgentSystemPrompt).where(
                AgentSystemPrompt.agent_type == agent_type,
                AgentSystemPrompt.is_active == True,
            )
            result = await self.db.execute(query)
            prompt_obj = result.scalar_one_or_none()
            if prompt_obj and prompt_obj.system_prompt:
                logger.info(
                    "Используется системный промпт из БД для %s (версия %s)",
                    agent_type,
                    prompt_obj.version,
                )
                return prompt_obj.system_prompt
        except Exception as exc:
            logger.warning(
                "Ошибка при получении системного промпта для %s: %s. Используется fallback.",
                agent_type,
                exc,
            )
        return fallback_prompt

    def _build_prompt(self, analysis_payload: dict[str, Any]) -> str:
        safe_payload = {
            "can_continue": analysis_payload.get("can_continue"),
            "quality_status": analysis_payload.get("quality_status"),
            "retry_hint": analysis_payload.get("retry_hint"),
            "analysis": _as_dict(analysis_payload.get("analysis")),
            "user_facing": _as_dict(analysis_payload.get("user_facing")),
            "style": analysis_payload.get("style"),
            "color_type": analysis_payload.get("color_type"),
        }
        return (
            "На основе structured photo analysis подготовь человекочитаемое описание внешности. "
            "Сначала опиши общее впечатление, затем лицо и линии, затем дай короткое название стилевого и цветового типа. "
            "Сохраняй дружелюбный премиальный тон GLAME.\n\n"
            f"INPUT JSON:\n{json.dumps(safe_payload, ensure_ascii=False, indent=2)}"
        )

    def _normalize_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("parse_error"):
            return {}

        bullets = _string_list(payload.get("bullets"))[:4]
        summary = str(payload.get("summary") or "").strip()
        appearance = str(payload.get("appearance") or "").strip()
        face = str(payload.get("face") or "").strip()
        style_type = str(payload.get("style_type") or "").strip()
        color_type = str(payload.get("color_type") or "").strip()

        if not any([summary, appearance, face, style_type, color_type, bullets]):
            return {}

        return {
            "summary": summary,
            "appearance": appearance,
            "face": face,
            "style_type": style_type,
            "color_type": color_type,
            "bullets": bullets,
        }

    def _enrich_with_eye_color(
        self,
        response: dict[str, Any],
        analysis_payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(response)
        analysis = _as_dict(analysis_payload.get("analysis"))
        color = _as_dict(analysis.get("colorAnalysis"))
        recommendations = _as_dict(analysis.get("recommendations"))
        eye_color = str(color.get("eyeColor") or "").strip().lower()
        if eye_color in {"", "unknown"}:
            return normalized

        bullets = _string_list(normalized.get("bullets"))[:4]
        if any("глаз" in bullet.lower() for bullet in bullets):
            normalized["bullets"] = bullets
            return normalized

        palette = _string_list(
            recommendations.get("stone_colors") or recommendations.get("recommendedStonePalette")
        )
        bullets.append(self._eye_color_bullet(eye_color, palette))
        normalized["bullets"] = bullets[:4]
        return normalized

    def _fallback_from_analysis(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        analysis = _as_dict(analysis_payload.get("analysis"))
        geometry = _as_dict(analysis.get("faceGeometry"))
        lines = _as_dict(analysis.get("lineAnalysis"))
        scale = _as_dict(analysis.get("appearanceScale"))
        color = _as_dict(analysis.get("colorAnalysis"))
        accent = _as_dict(analysis.get("accentZones"))

        face_shape = self._face_shape_text(geometry.get("faceShape"))
        vertical = self._vertical_text(geometry.get("overallVertical"))
        line_text = self._line_text(lines.get("lineType"))
        scale_text = self._scale_text(scale.get("overallAppearanceScale"))
        undertone = self._undertone_text(color.get("skinUndertone"))
        contrast = self._contrast_text(color.get("contrastLevel"))
        accent_text = self._accent_text(accent.get("primaryAccentZone"))
        eye_color = self._label_text(color.get("eyeColor"))
        hair_color = self._label_text(color.get("hairColor"))

        style_type = self._style_type(lines.get("lineType"), scale.get("overallAppearanceScale"))
        color_type = self._color_type(color.get("skinUndertone"), color.get("contrastLevel"))

        summary = (
            f"Внешность считывается как {line_text} и {scale_text}. "
            f"Форма лица ближе к {face_shape}, а общее впечатление выглядит {vertical}. "
            f"Лучше всего поддерживать акцент в зоне {accent_text} и выбирать украшения, которые не спорят с природной мягкостью линий."
        )
        appearance = (
            f"Общий типаж выглядит {line_text}, с {scale_text} и спокойным визуальным балансом. "
            f"Цветовое впечатление ближе к {undertone} гамме и {contrast} контрасту."
        )
        face = (
            f"Лицо ближе к {face_shape}, линии воспринимаются как {line_text}, "
            f"поэтому лучше работают мягкие формы и выверенный акцент возле лица. "
            f"Цвет глаз: {eye_color}. Цвет волос: {hair_color}."
        )
        bullets = [
            f"Типаж ближе к {style_type.lower()}.",
            f"Цветовое впечатление ближе к {color_type.lower()}.",
            f"Основной акцент лучше держать в зоне {accent_text}.",
        ]
        return {
            "summary": summary,
            "appearance": appearance,
            "face": face,
            "style_type": style_type,
            "color_type": color_type,
            "bullets": bullets,
        }

    def _retry_payload(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        retry_hint = str(analysis_payload.get("retry_hint") or "").strip()
        summary = "Сначала нужно получить более подходящее фото, чтобы описание внешности было точным."
        bullets = [
            retry_hint or "Нужен более удачный портрет для точного разбора внешности.",
            "После новой загрузки мы сначала проверим качество фото, а затем соберём описание внешности.",
        ]
        return {
            "summary": summary,
            "appearance": "",
            "face": "",
            "style_type": "",
            "color_type": "",
            "bullets": [item for item in bullets if item],
            "source": "retry",
            "agent_type": self.AGENT_TYPE,
        }

    def _face_shape_text(self, value: Any) -> str:
        mapping = {
            "oval": "овальной форме",
            "round": "округлой форме",
            "elongated": "вытянутой форме",
            "square": "более графичной форме",
            "heart": "форме с мягким акцентом в верхней части лица",
        }
        return mapping.get(str(value or "").strip().lower(), "сбалансированной форме")

    def _vertical_text(self, value: Any) -> str:
        mapping = {
            "elongated": "более вытянутым",
            "compact": "более компактным",
            "balanced": "сбалансированным",
        }
        return mapping.get(str(value or "").strip().lower(), "сбалансированным")

    def _line_text(self, value: Any) -> str:
        mapping = {
            "graphic": "более графично и собранно",
            "organic": "мягко и естественно",
            "soft_geometric": "мягко, но структурно",
        }
        return mapping.get(str(value or "").strip().lower(), "спокойно и собранно")

    def _scale_text(self, value: Any) -> str:
        mapping = {
            "mini": "миниатюрным масштабом черт",
            "medium": "средним масштабом черт",
            "large": "более крупным масштабом черт",
            "statement": "акцентным масштабом черт",
        }
        return mapping.get(str(value or "").strip().lower(), "средним масштабом черт")

    def _undertone_text(self, value: Any) -> str:
        mapping = {
            "warm": "теплой",
            "cool": "холодной",
            "neutral": "нейтральной",
        }
        return mapping.get(str(value or "").strip().lower(), "нейтральной")

    def _contrast_text(self, value: Any) -> str:
        mapping = {
            "low": "мягкому",
            "medium": "умеренному",
            "high": "более выраженному",
        }
        return mapping.get(str(value or "").strip().lower(), "умеренному")

    def _accent_text(self, value: Any) -> str:
        mapping = {
            "earrings": "лица и серёг",
            "necklace": "шеи и колье",
            "rings": "кистей и колец",
            "bracelets": "запястий и браслетов",
            "mixed": "нескольких зон сразу",
        }
        return mapping.get(str(value or "").strip().lower(), "лица")

    def _style_type(self, line_type: Any, scale_value: Any) -> str:
        line = str(line_type or "").strip().lower()
        scale = str(scale_value or "").strip().lower()
        if line == "graphic":
            return "Графичный элегантный тип"
        if line == "organic":
            return "Мягкий естественный тип"
        if scale in {"large", "statement"}:
            return "Выразительный спокойный тип"
        return "Элегантный мягкий тип"

    def _color_type(self, undertone: Any, contrast: Any) -> str:
        tone = str(undertone or "").strip().lower()
        contrast_value = str(contrast or "").strip().lower()
        if tone == "warm" and contrast_value == "high":
            return "Тёплый контрастный тип"
        if tone == "warm":
            return "Тёплый мягкий тип"
        if tone == "cool" and contrast_value == "high":
            return "Холодный контрастный тип"
        if tone == "cool":
            return "Холодный мягкий тип"
        return "Нейтральный сбалансированный тип"

    def _label_text(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        mapping = {
            "brown": "карий",
            "blue": "голубой",
            "green": "зелёный",
            "gray": "серый",
            "hazel": "ореховый",
            "black": "тёмный",
            "blonde": "светлый",
            "red": "рыжеватый",
            "auburn": "каштановый",
        }
        return mapping.get(text, text or "не считывается уверенно")

    def _eye_color_bullet(self, eye_color: str, palette: list[str]) -> str:
        eye_text = self._eye_color_phrase(eye_color)
        palette_hint = "тёплые мягкие камни"
        if any(item in palette for item in ["peach", "pastel", "soft"]):
            palette_hint = "тёплые камни вроде янтаря, цитрина и мягких персиковых оттенков"
        elif any(item in palette for item in ["deep", "contrast", "dark"]):
            palette_hint = "более глубокие и контрастные камни"
        elif any(item in palette for item in ["balanced", "warm"]):
            palette_hint = "спокойные тёплые камни средней насыщенности"
        return f"Глаза {eye_text}: {palette_hint} красиво подчеркнут их глубину."

    def _eye_color_phrase(self, eye_color: str) -> str:
        mapping = {
            "brown": "карего оттенка",
            "blue": "голубого оттенка",
            "green": "зелёного оттенка",
            "gray": "серого оттенка",
            "hazel": "орехового оттенка",
            "black": "тёмного оттенка",
        }
        normalized = str(eye_color or "").strip().lower()
        return mapping.get(normalized, "выразительного оттенка")
