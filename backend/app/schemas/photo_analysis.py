from typing import Any

from pydantic import BaseModel, Field


class PhotoAnalysisApiResponse(BaseModel):
    success: bool = True
    can_continue: bool = True
    quality_status: str = "ok"
    retry_hint: str | None = None
    analysis: dict[str, Any] = Field(default_factory=dict)
    user_facing: dict[str, Any] = Field(default_factory=dict)
    human_readable: dict[str, Any] = Field(default_factory=dict)
    recommended_products: list[dict[str, Any]] = Field(default_factory=list)
    saved_photo_url: str | None = None
    saved_analysis_url: str | None = None

    # Legacy-compatible fields kept for current clients and gradual rollout.
    color_type: str = "универсальный"
    style: str = "классический"
    features: dict[str, Any] = Field(default_factory=dict)
    recommendations: dict[str, Any] = Field(default_factory=dict)


class PhotoAnalysisMlRequest(BaseModel):
    filename: str | None = None


class PhotoAnalysisMlResponse(BaseModel):
    success: bool = True
    can_continue: bool = True
    quality_status: str = "ok"
    retry_hint: str | None = None
    analysis: dict[str, Any] = Field(default_factory=dict)
