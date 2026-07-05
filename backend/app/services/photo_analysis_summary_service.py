from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


class PhotoAnalysisSummaryService:
    def build_user_facing(self, analysis: dict[str, Any]) -> dict[str, Any]:
        recommendations = _as_dict(analysis.get("recommendations"))
        accent = _as_dict(analysis.get("accentZones"))
        scale = recommendations.get("recommendedScale", "medium")
        shapes = _string_list(recommendations.get("recommendedShapes"))
        metals = _string_list(recommendations.get("recommendedMetals"))
        textures = _string_list(recommendations.get("recommendedTextures"))
        primary = str(accent.get("primaryAccentZone") or recommendations.get("primaryCategory") or "earrings")

        shape_text = self._shape_text(shapes)
        metal_text = self._metal_text(metals)
        texture_text = self._texture_text(textures)

        summary = (
            f"Вам подойдут украшения {self._scale_text(scale)}, "
            f"{shape_text} и {texture_text}. "
            f"Лучше всего сделать акцент на {self._primary_zone_text(primary)}. "
            f"Лучше всего они будут смотреться в {metal_text}."
        )

        bullets = [
            self._earring_bullet(recommendations),
            self._shape_bullet(shapes),
            self._metal_bullet(metals),
        ]

        return {
            "summary": summary,
            "bullets": [item for item in bullets if item],
        }

    def build_retry_user_facing(self, retry_hint: str | None = None) -> dict[str, Any]:
        summary = "Фото пока не подходит для точного подбора украшений."
        bullets = [
            retry_hint or "Нужно загрузить фото с одним лицом крупным планом и при ровном свете.",
            "Лучше использовать спокойный портрет без коллажа и без полного роста.",
            "Если возможно, выберите кадр, где лицо занимает больше места в кадре.",
        ]
        return {
            "summary": summary,
            "bullets": [item for item in bullets if item],
        }

    def _scale_text(self, scale: Any) -> str:
        value = str(scale or "medium").strip()
        mapping = {
            "mini": "миниатюрного масштаба",
            "medium": "среднего масштаба",
            "large": "крупнее среднего масштаба",
            "statement": "акцентного масштаба",
        }
        return mapping.get(value, "среднего масштаба")

    def _shape_text(self, shapes: list[str]) -> str:
        if any(item in {"oval", "drop", "soft_geometry"} for item in shapes):
            return "мягкой геометрии"
        if "clean_line" in shapes or "geometry" in shapes:
            return "чистой графики"
        return "спокойной формы"

    def _metal_text(self, metals: list[str]) -> str:
        if metals == ["silver"]:
            return "серебре и холодных сочетаниях"
        if metals == ["gold"]:
            return "золоте и теплых сочетаниях"
        return "смешанных металлах и деликатных сочетаниях"

    def _texture_text(self, textures: list[str]) -> str:
        if "mirror" in textures:
            return "деликатного блеска"
        if "smooth" in textures:
            return "гладкой фактуры"
        return "спокойной фактуры"

    def _earring_bullet(self, recommendations: dict[str, Any]) -> str:
        lengths = _string_list(recommendations.get("recommendedEarringLength"))
        if "long" in lengths:
            return "Можно добавить более вытянутые серьги для мягкого вертикального акцента."
        if "medium" in lengths:
            return "Серьги средней длины будут смотреться гармонично и спокойно."
        return "Лучше выбирать компактные серьги без лишней тяжести."

    def _shape_bullet(self, shapes: list[str]) -> str:
        if any(item in {"oval", "drop", "soft_geometry"} for item in shapes):
            return "Мягкая геометрия и вытянутые формы поддержат линии лица."
        return "Чистые формы без перегруза сохранят баланс образа."

    def _metal_bullet(self, metals: list[str]) -> str:
        if metals == ["silver"]:
            return "Холодные металлы будут смотреться наиболее естественно."
        if metals == ["gold"]:
            return "Теплые металлы будут смотреться наиболее естественно."
        return "Смешанные металлы и мягкий блеск сохранят универсальность подбора."

    def _primary_zone_text(self, value: str) -> str:
        mapping = {
            "earrings": "серьги",
            "necklace": "зоне шеи",
            "rings": "кольца",
            "bracelets": "браслеты",
            "mixed": "нескольких зонах",
        }
        return mapping.get(value, "зоне лица")


photo_analysis_summary_service = PhotoAnalysisSummaryService()
