import logging
from typing import Any, Awaitable, Callable

from app.services.jewelry_recommendation_mapper import (
    jewelry_recommendation_mapper,
)
from app.services.ml_inference_client import ml_inference_client
from app.services.photo_analysis_summary_service import (
    photo_analysis_summary_service,
)


logger = logging.getLogger(__name__)

LegacyAnalysisProvider = Callable[[bytes, str | None], Awaitable[dict[str, Any]]]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class PhotoAnalysisOrchestrator:
    async def analyze_photo(
        self,
        photo_data: bytes,
        filename: str | None = None,
        legacy_provider: LegacyAnalysisProvider | None = None,
    ) -> dict[str, Any]:
        ml_payload = await ml_inference_client.analyze_face(
            photo_data=photo_data,
            filename=filename,
        )

        if ml_payload:
            envelope = self._normalize_ml_payload(ml_payload)
        else:
            legacy_payload = (
                await legacy_provider(photo_data, filename)
                if legacy_provider
                else {}
            )
            envelope = self._build_from_legacy(legacy_payload)

        analysis = jewelry_recommendation_mapper.enrich(
            _as_dict(envelope.get("analysis"))
        )
        quality = self._resolve_quality(envelope, analysis)
        if quality["can_continue"]:
            user_facing = photo_analysis_summary_service.build_user_facing(analysis)
        else:
            user_facing = photo_analysis_summary_service.build_retry_user_facing(
                quality["retry_hint"]
            )

        recommendations = _as_dict(analysis.get("recommendations"))
        legacy_fields = self._legacy_projection(analysis)

        return {
            "success": True,
            "can_continue": quality["can_continue"],
            "quality_status": quality["quality_status"],
            "retry_hint": quality["retry_hint"],
            "analysis": analysis,
            "user_facing": user_facing,
            "color_type": legacy_fields["color_type"],
            "style": legacy_fields["style"],
            "features": legacy_fields["features"],
            "recommendations": recommendations,
        }

    def _normalize_ml_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = _as_dict(payload.get("analysis"))
        if not analysis:
            analysis = self._build_canonical_from_legacy(payload)
        return {
            "analysis": analysis,
            "can_continue": payload.get("can_continue", True),
            "quality_status": payload.get("quality_status", "ok"),
            "retry_hint": payload.get("retry_hint"),
        }

    def _build_from_legacy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "analysis": self._build_canonical_from_legacy(payload),
            "can_continue": True,
            "quality_status": "ok",
            "retry_hint": None,
        }

    def _build_canonical_from_legacy(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        features = _as_dict(payload.get("features"))
        recommendations = _as_dict(payload.get("recommendations"))

        recommended_metals = recommendations.get("metal_colors")
        if not isinstance(recommended_metals, list):
            recommended_metals = ["silver", "mixed"]

        recommended_styles = recommendations.get("styles")
        if not isinstance(recommended_styles, list):
            recommended_styles = ["элегантный", "классический"]

        return {
            "version": "1.0",
            "photoQuality": {
                "faceDetected": True,
                "singlePerson": True,
                "faceVisibleLarge": True,
                "sharpness": "medium",
                "lightQuality": "medium",
                "filterDetected": False,
                "headTiltStrong": False,
                "earVisible": "partial",
                "neckVisible": "partial",
            },
            "faceGeometry": {
                "faceShape": features.get("face_shape", "unknown"),
                "faceLength": "balanced",
                "faceWidth": "balanced",
                "jawlineType": "soft",
                "cheekboneProminence": "medium",
                "chinType": "soft",
                "foreheadProportion": "balanced",
                "overallVertical": "balanced",
                "overallHorizontal": "balanced",
            },
            "appearanceScale": {
                "overallAppearanceScale": "medium",
                "featureScale": "medium",
                "eyeScale": "medium",
                "lipScale": "medium",
                "noseScale": "medium",
                "featureDensity": "medium",
                "allowedJewelryScale": "medium",
                "riskOfOverload": "medium",
            },
            "lineAnalysis": {
                "lineType": "soft_geometric",
                "dominantLineDirection": "elongated",
                "softnessLevel": "medium",
                "graphicLevel": "medium",
                "visualStrictness": "balanced",
                "visualNaturalness": "medium",
            },
            "colorAnalysis": {
                "eyeColor": features.get("eye_color", "unknown"),
                "hairColor": features.get("hair_color", "unknown"),
                "hairDepth": "medium",
                "skinUndertone": features.get("skin_tone", "unknown"),
                "appearanceLightness": "medium",
                "contrastLevel": "medium",
                "appearanceBrightness": "soft",
                "recommendedMetal": self._normalize_recommended_metal(
                    recommended_metals
                ),
                "recommendedStonePalette": recommendations.get(
                    "stone_colors", ["soft"]
                ),
            },
            "textureAnalysis": {
                "skinTextureVisual": "smooth",
                "frecklesVisible": "unknown",
                "fineLinesVisible": "unknown",
                "overallTexture": "soft",
                "textureContrast": "medium",
                "recommendedTextures": ["smooth", "mirror"],
                "textureOverloadRisk": "low",
            },
            "earAndLobeAnalysis": {
                "earVisibility": "partial",
                "earlobeSize": "medium",
                "earlobeType": "unknown",
                "earlobeCondition": "unknown",
                "piercingCountVisible": "unknown",
                "currentEarringFit": "unclear",
                "recommendedEarringWeight": "light_medium",
                "recommendedEarringClosure": ["stud", "english_lock"],
                "heavyEarringRisk": "medium",
            },
            "neckAnalysis": {
                "neckLength": "medium",
                "neckVisibility": "partial",
                "neckDelicacy": "medium",
                "recommendedNecklaceLength": ["short", "medium"],
                "shorteningRisk": "medium",
                "verticalAccentNeeded": "optional",
            },
            "accentZones": {
                "primaryAccentZone": "earrings",
                "secondaryAccentZone": "necklace",
                "accentNearFace": "yes",
                "accentOnNeck": "moderate",
                "accentOnHands": "optional",
            },
            "recommendations": {
                "primaryCategory": "earrings",
                "recommendedCategories": ["earrings", "necklace", "rings"],
                "recommendedScale": "medium",
                "recommendedEarringLength": ["short", "medium"],
                "recommendedEarringWeight": "light_medium",
                "recommendedNecklaceLength": ["short", "medium"],
                "recommendedShapes": ["oval", "drop", "soft_geometry"],
                "recommendedTextures": ["smooth", "mirror"],
                "recommendedMetals": recommended_metals,
                "avoidAsPrimary": ["too_heavy", "too_tiny"],
                "styleHints": recommended_styles,
            },
            "debug": {
                "pipelineVersion": "legacy-vision-fallback",
                "provider": "look_tryon_service",
            },
        }

    def _resolve_quality(
        self,
        envelope: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        quality = _as_dict(analysis.get("photoQuality"))
        can_continue = envelope.get("can_continue")
        if not isinstance(can_continue, bool):
            can_continue = bool(quality.get("faceDetected", True)) and bool(
                quality.get("singlePerson", True)
            ) and bool(quality.get("faceVisibleLarge", True))

        quality_status = envelope.get("quality_status")
        if not isinstance(quality_status, str) or not quality_status.strip():
            quality_status = "ok" if can_continue else "retry_required"

        retry_hint = envelope.get("retry_hint")
        if not isinstance(retry_hint, str) or not retry_hint.strip():
            retry_hint = None
        if not retry_hint and not can_continue:
            retry_hint = (
                "На фото должно быть одно лицо крупным планом и при ровном свете."
            )

        return {
            "can_continue": can_continue,
            "quality_status": quality_status,
            "retry_hint": retry_hint,
        }

    def _legacy_projection(self, analysis: dict[str, Any]) -> dict[str, Any]:
        color = _as_dict(analysis.get("colorAnalysis"))
        geometry = _as_dict(analysis.get("faceGeometry"))
        recommendations = _as_dict(analysis.get("recommendations"))

        style_hints = recommendations.get("styleHints")
        if isinstance(style_hints, list) and style_hints:
            style = str(style_hints[0])
        else:
            style = "классический"

        return {
            "color_type": str(color.get("skinUndertone", "универсальный")),
            "style": style,
            "features": {
                "face_shape": geometry.get("faceShape", "unknown"),
                "hair_color": color.get("hairColor", "unknown"),
                "eye_color": color.get("eyeColor", "unknown"),
                "skin_tone": color.get("skinUndertone", "unknown"),
            },
        }

    def _normalize_recommended_metal(self, values: list[Any]) -> str:
        normalized = [str(item).strip().lower() for item in values if str(item).strip()]
        if normalized == ["silver"]:
            return "silver"
        if normalized == ["gold"]:
            return "gold"
        return "mixed"


photo_analysis_orchestrator = PhotoAnalysisOrchestrator()
