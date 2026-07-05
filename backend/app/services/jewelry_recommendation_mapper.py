from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class JewelryRecommendationMapper:
    def enrich(self, analysis: dict[str, Any]) -> dict[str, Any]:
        result = dict(analysis or {})

        color = _as_dict(result.get("colorAnalysis"))
        lines = _as_dict(result.get("lineAnalysis"))
        scale = _as_dict(result.get("appearanceScale"))
        ear = _as_dict(result.get("earAndLobeAnalysis"))
        neck = _as_dict(result.get("neckAnalysis"))
        accent = _as_dict(result.get("accentZones"))
        recommendations = _as_dict(result.get("recommendations"))

        if not accent:
            accent = {
                "primaryAccentZone": "earrings",
                "secondaryAccentZone": "necklace",
                "accentNearFace": "yes",
                "accentOnNeck": "moderate",
                "accentOnHands": "optional",
            }

        if not recommendations:
            recommended_scale = scale.get("allowedJewelryScale") or "medium"
            line_type = lines.get("lineType") or "soft_geometric"
            recommended_shapes = self._recommended_shapes(line_type)
            recommended_metals = self._recommended_metals(color)
            recommended_textures = self._recommended_textures(result)
            heavy_earring_risk = ear.get("heavyEarringRisk", "medium")
            avoid = ["too_tiny"]
            if heavy_earring_risk in {"medium", "high"}:
                avoid.append("too_heavy")

            recommendations = {
                "primaryCategory": accent.get("primaryAccentZone", "earrings"),
                "recommendedCategories": self._recommended_categories(
                    accent.get("primaryAccentZone"),
                    accent.get("secondaryAccentZone"),
                ),
                "recommendedScale": recommended_scale,
                "recommendedEarringLength": self._recommended_earring_length(
                    result
                ),
                "recommendedEarringWeight": ear.get(
                    "recommendedEarringWeight", "light_medium"
                ),
                "recommendedNecklaceLength": neck.get(
                    "recommendedNecklaceLength", ["short", "medium"]
                ),
                "recommendedShapes": recommended_shapes,
                "recommendedTextures": recommended_textures,
                "recommendedMetals": recommended_metals,
                "avoidAsPrimary": avoid,
            }

        recommendations = self._ensure_legacy_aliases(recommendations, result)
        result["accentZones"] = accent
        result["recommendations"] = recommendations
        return result

    def _ensure_legacy_aliases(
        self,
        recommendations: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(recommendations)
        if not isinstance(result.get("metal_colors"), list):
            result["metal_colors"] = list(self._recommended_metals(_as_dict(analysis.get("colorAnalysis"))))

        color = _as_dict(analysis.get("colorAnalysis"))
        if not isinstance(result.get("stone_colors"), list):
            palette = color.get("recommendedStonePalette")
            if isinstance(palette, list) and palette:
                result["stone_colors"] = [str(item) for item in palette if str(item).strip()]
            else:
                result["stone_colors"] = ["soft"]

        if not isinstance(result.get("styles"), list):
            line_type = str(_as_dict(analysis.get("lineAnalysis")).get("lineType") or "soft_geometric")
            style_hints = {
                "graphic": ["графичный", "структурный"],
                "organic": ["органичный", "мягкий"],
                "soft_geometric": ["элегантный", "спокойный"],
            }
            result["styles"] = style_hints.get(line_type, ["элегантный", "классический"])
        return result

    def _recommended_categories(
        self,
        primary: Any,
        secondary: Any,
    ) -> list[str]:
        values = []
        for item in [primary, secondary, "rings"]:
            if isinstance(item, str) and item and item not in values:
                values.append(item)
        return values or ["earrings", "necklace", "rings"]

    def _recommended_shapes(self, line_type: str) -> list[str]:
        if line_type == "graphic":
            return ["clean_line", "elongated", "geometry"]
        if line_type == "organic":
            return ["organic", "soft_geometry", "drop"]
        return ["oval", "drop", "soft_geometry", "clean_line"]

    def _recommended_metals(self, color: dict[str, Any]) -> list[str]:
        metal = color.get("recommendedMetal")
        if metal == "silver":
            return ["silver"]
        if metal == "gold":
            return ["gold"]
        return ["silver", "mixed"]

    def _recommended_textures(self, analysis: dict[str, Any]) -> list[str]:
        texture = _as_dict(analysis.get("textureAnalysis"))
        values = texture.get("recommendedTextures")
        if isinstance(values, list) and values:
            return [str(item) for item in values if str(item).strip()]
        return ["smooth", "mirror", "delicate_hammered"]

    def _recommended_earring_length(
        self,
        analysis: dict[str, Any],
    ) -> list[str]:
        geometry = _as_dict(analysis.get("faceGeometry"))
        vertical = geometry.get("overallVertical")
        if vertical == "elongated":
            return ["short"]
        if vertical == "compact":
            return ["medium", "long"]
        return ["short", "medium"]


jewelry_recommendation_mapper = JewelryRecommendationMapper()
