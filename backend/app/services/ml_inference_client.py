import logging
import os
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class MLInferenceClient:
    def __init__(self):
        self.base_url = (os.getenv("ML_INFERENCE_URL") or "").rstrip("/")
        self.timeout = float(os.getenv("ML_INFERENCE_TIMEOUT_SECONDS", "45.0"))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def analyze_face(
        self,
        photo_data: bytes,
        filename: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/analyze-face",
                    files={
                        "photo": (
                            filename or "photo.jpg",
                            photo_data,
                            "image/jpeg",
                        )
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "ML inference analyze-face failed with status %s: %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return None
        except Exception as exc:
            logger.warning("ML inference analyze-face failed: %s", exc)
            return None

        if not isinstance(payload, dict):
            logger.warning("ML inference returned non-dict payload")
            return None
        return payload


ml_inference_client = MLInferenceClient()
