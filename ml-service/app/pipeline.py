from __future__ import annotations

from io import BytesIO
import logging
from typing import Any

from PIL import Image, ImageStat

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None

try:
    import mediapipe as mp  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    mp = None

try:
    if mp is not None:
        mp_solutions = getattr(mp, "solutions", None)
        if mp_solutions is None:
            from mediapipe.python import solutions as mp_solutions  # type: ignore
    else:
        mp_solutions = None
except Exception:  # pragma: no cover - optional runtime dependency
    mp_solutions = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    np = None


FACE_TOP = 10
FACE_CHIN = 152
LEFT_FACE = 234
RIGHT_FACE = 454
LEFT_CHEEK = 93
RIGHT_CHEEK = 323
LEFT_JAW = 172
RIGHT_JAW = 397
LEFT_EYE_OUTER = 33
LEFT_EYE_INNER = 133
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263
LEFT_EYE_UPPER = 159
LEFT_EYE_LOWER = 145
RIGHT_EYE_UPPER = 386
RIGHT_EYE_LOWER = 374
LEFT_BROW_UPPER = 105
RIGHT_BROW_UPPER = 334
MOUTH_LEFT = 61
MOUTH_RIGHT = 291
UPPER_LIP = 13
NOSE_LEFT = 98
NOSE_RIGHT = 327
NOSE_BASE = 2


logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _quality_bucket(value: float, low: float, medium: float) -> str:
    if value < low:
        return "poor"
    if value < medium:
        return "medium"
    return "good"


def _quality_failure_reasons(photo_quality: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not photo_quality.get("faceDetected", True):
        reasons.append("не удалось уверенно распознать лицо")
    if not photo_quality.get("singlePerson", True):
        reasons.append("в кадре должно быть только одно лицо")
    if not photo_quality.get("faceVisibleLarge", True):
        reasons.append("лицо должно быть крупнее и ближе к камере")
    if photo_quality.get("lightQuality") == "poor":
        reasons.append("нужно более ровное освещение без сильных теней")
    if photo_quality.get("sharpness") == "poor":
        reasons.append("фото должно быть более четким")
    if photo_quality.get("headTiltStrong"):
        reasons.append("лучше держать голову прямо, без сильного наклона")
    return reasons


def _quality_retry_hint(photo_quality: dict[str, Any]) -> str | None:
    reasons = _quality_failure_reasons(photo_quality)
    if not reasons:
        return None
    return "Чтобы подбор был точнее: " + "; ".join(reasons) + "."


def _determine_metal(brightness: float, warmth: float) -> tuple[str, list[str]]:
    if warmth >= 0.55:
        return "gold", ["gold"]
    if brightness >= 0.7 and warmth <= 0.45:
        return "silver", ["silver"]
    return "mixed", ["silver", "mixed"]


def _recommended_shapes(aspect_ratio: float) -> list[str]:
    if aspect_ratio >= 1.22:
        return ["clean_line", "elongated", "drop"]
    if aspect_ratio <= 0.92:
        return ["oval", "soft_geometry", "drop"]
    return ["oval", "drop", "soft_geometry", "clean_line"]


def _appearance_scale(width: int, height: int) -> str:
    short_side = min(width, height)
    if short_side < 720:
        return "delicate"
    if short_side < 1200:
        return "medium"
    return "expressive"


def _px(
    landmarks: list[tuple[int, int]],
    index: int,
) -> tuple[int, int]:
    if 0 <= index < len(landmarks):
        return landmarks[index]
    return 0, 0


def _distance(
    a: tuple[int, int],
    b: tuple[int, int],
) -> float:
    ax, ay = a
    bx, by = b
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _safe_ratio(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def _crop_np(
    image_rgb: Any,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> Any:
    if np is None:
        return None
    height, width = image_rgb.shape[:2]
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return image_rgb[y1:y2, x1:x2]


def _concat_regions_horizontally(left: Any, right: Any) -> Any:
    if np is None:
        return None
    if left is None and right is None:
        return None
    if left is None:
        return right
    if right is None:
        return left

    left_h = left.shape[0]
    right_h = right.shape[0]
    target_h = min(left_h, right_h)
    if target_h <= 0:
        return left

    if left_h != target_h:
        top = max((left_h - target_h) // 2, 0)
        left = left[top : top + target_h, :]
    if right_h != target_h:
        top = max((right_h - target_h) // 2, 0)
        right = right[top : top + target_h, :]

    return np.concatenate([left, right], axis=1)


def _image_bytes_from_rgb(image_rgb: Any) -> bytes:
    buf = BytesIO()
    Image.fromarray(image_rgb).save(buf, format="JPEG")
    return buf.getvalue()


def _mean_rgb(region: Any) -> tuple[float, float, float]:
    if np is None or region is None or getattr(region, "size", 0) == 0:
        return 0.0, 0.0, 0.0
    mean = region.mean(axis=(0, 1))
    return float(mean[0]), float(mean[1]), float(mean[2])


def _median_rgb(region: Any) -> tuple[float, float, float]:
    if np is None or region is None or getattr(region, "size", 0) == 0:
        return 0.0, 0.0, 0.0
    pixels = region.reshape(-1, 3)
    median = np.median(pixels, axis=0)
    return float(median[0]), float(median[1]), float(median[2])


def _rgb_brightness(mean_rgb: tuple[float, float, float]) -> float:
    return _clamp(sum(mean_rgb) / (255 * 3), 0.0, 1.0)


def _region_lab_lightness(region: Any) -> float | None:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return None
    lab = cv2.cvtColor(region, cv2.COLOR_RGB2LAB)
    return round(float(lab[:, :, 0].mean()) / 255.0 * 100.0, 3)


def _region_lab_stats(region: Any) -> dict[str, float | None]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return {"lightness": None, "a": None, "b": None}
    lab = cv2.cvtColor(region, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    return {
        "lightness": round(float(l_channel.mean()) / 255.0 * 100.0, 3),
        "a": round(float(a_channel.mean()) - 128.0, 3),
        "b": round(float(b_channel.mean()) - 128.0, 3),
    }


def _median_hsv(region: Any) -> tuple[float | None, float | None, float | None]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return None, None, None
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV).reshape(-1, 3)
    if hsv.size == 0:
        return None, None, None
    return (
        float(np.median(hsv[:, 0])) * 2.0,
        float(np.median(hsv[:, 1])),
        float(np.median(hsv[:, 2])),
    )


def _hue_distance(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 180.0
    diff = abs(a - b)
    if np is not None and hasattr(diff, "shape"):
        return np.minimum(diff, 360.0 - diff)
    return min(diff, 360.0 - diff)


def _variance_contrast(region: Any) -> float:
    if np is None or region is None or getattr(region, "size", 0) == 0:
        return 0.0
    return _clamp(float(region.std()) / 64.0, 0.0, 1.0)


def _laplacian_sharpness(region: Any) -> float:
    if region is None or getattr(region, "size", 0) == 0:
        return 0.0
    if cv2 is not None and np is not None:
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        return _clamp(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 800.0, 0.0, 1.0)
    return _variance_contrast(region)


def _center_eye_pixels(region: Any) -> Any:
    if region is None or getattr(region, "size", 0) == 0 or np is None:
        return None
    height, width = region.shape[:2]
    if height < 8 or width < 8:
        return None

    x1 = int(width * 0.16)
    x2 = int(width * 0.84)
    y1 = int(height * 0.2)
    y2 = int(height * 0.8)
    cropped = region[y1:y2, x1:x2]
    if cropped.size == 0:
        return None

    crop_h, crop_w = cropped.shape[:2]
    yy, xx = np.ogrid[:crop_h, :crop_w]
    cx = crop_w / 2.0
    cy = crop_h / 2.0
    rx = max(crop_w * 0.46, 1.0)
    ry = max(crop_h * 0.34, 1.0)
    mask = (((xx - cx) ** 2) / (rx**2) + ((yy - cy) ** 2) / (ry**2)) <= 1.0
    pixels = cropped[mask]
    if pixels.size == 0:
        return None
    return pixels.reshape(-1, 3)


def _eye_color_from_hsv(hue: float, sat: float, val: float) -> str:
    if sat < 20:
        return "gray" if val < 155 else "unknown"
    if 90 <= hue <= 138:
        return "blue"
    if 38 <= hue < 90:
        return "green"
    if 17 <= hue < 38:
        return "hazel"
    if hue < 17 or hue >= 170:
        return "brown" if val < 165 else "hazel"
    return "brown" if val < 150 else "hazel"


def _classify_eye_color(region: Any) -> str:
    if (
        region is None
        or getattr(region, "size", 0) == 0
        or cv2 is None
        or np is None
    ):
        return "unknown"

    if _variance_contrast(region) < 0.06:
        return "unknown"

    center_pixels = _center_eye_pixels(region)
    if center_pixels is None or len(center_pixels) < 24:
        return "unknown"

    hsv = cv2.cvtColor(center_pixels.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    h = hsv[:, 0].astype(np.float32) * 2.0
    s = hsv[:, 1].astype(np.float32)
    v = hsv[:, 2].astype(np.float32)

    low_v = float(np.percentile(v, 12))
    high_v = float(np.percentile(v, 88))
    candidate_mask = (
        (v >= max(18.0, low_v))
        & (v <= min(205.0, high_v))
        & (s >= 16)
    )
    candidate_pixels = hsv[candidate_mask]
    if len(candidate_pixels) < 20:
        candidate_pixels = hsv[(v >= 20) & (v <= 205)]
    if len(candidate_pixels) < 20:
        return "unknown"

    sample = candidate_pixels.astype(np.float32)
    cluster_count = 3 if len(sample) >= 90 else 2
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        16,
        1.0,
    )
    _, labels, centers = cv2.kmeans(
        sample,
        cluster_count,
        None,
        criteria,
        4,
        cv2.KMEANS_PP_CENTERS,
    )
    counts = np.bincount(labels.flatten(), minlength=cluster_count).astype(np.float32)
    best_score = None
    best_center = None
    for idx, center in enumerate(centers):
        hue = float(center[0]) * 2.0
        sat = float(center[1])
        val = float(center[2])
        score = (
            sat * 0.9
            + counts[idx] * 0.35
            - abs(val - 108.0) * 0.22
            - (35.0 if val > 190 else 0.0)
        )
        if best_score is None or score > best_score:
            best_score = score
            best_center = (hue, sat, val)

    if best_center is None:
        return "unknown"
    hue, sat, val = best_center
    return _eye_color_from_hsv(hue, sat, val)


def _classify_hair_color(region: Any) -> tuple[str, str]:
    if (
        region is None
        or getattr(region, "size", 0) == 0
        or cv2 is None
        or np is None
    ):
        return "unknown", "unknown"

    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    pixels = hsv.reshape(-1, 3)
    if pixels.size == 0:
        return "unknown", "unknown"

    h = pixels[:, 0].astype(np.float32)
    s = pixels[:, 1].astype(np.float32)
    v = pixels[:, 2].astype(np.float32)
    overall_sat = float(np.median(s))
    overall_val = float(np.median(v))

    dark_threshold = float(np.percentile(v, 62))
    candidate_mask = ((v <= dark_threshold) & (s >= 12)) | (v <= float(np.percentile(v, 40)))
    candidate_pixels = pixels[candidate_mask]
    if len(candidate_pixels) < 40:
        candidate_pixels = pixels

    hue = float(np.median(candidate_pixels[:, 0]))
    sat = float(np.median(candidate_pixels[:, 1]))
    val = float(np.median(candidate_pixels[:, 2]))

    brightness = _clamp(val / 255.0, 0.0, 1.0)
    overall_brightness = _clamp(overall_val / 255.0, 0.0, 1.0)
    if brightness < 0.2:
        return "black", "dark"
    if brightness < 0.32:
        return "dark_brown", "dark"

    if overall_brightness > 0.72 and overall_sat < 135:
        return "blonde", "light"

    if 5 <= hue <= 18 and sat >= 55 and 0.35 <= brightness <= 0.62 and overall_brightness <= 0.68:
        return "red", "medium"

    if brightness > 0.46:
        return "light_brown", "medium"
    return "brown", "medium"


def _hair_secondary_tone(region: Any) -> str:
    hue, sat, val = _median_hsv(region)
    if hue is None or sat is None or val is None:
        return "neutral"
    if sat < 28 and val >= 120:
        return "ash"
    if 8 <= hue <= 32 and sat >= 65:
        return "copper"
    if 24 <= hue <= 58 and sat >= 35:
        return "golden"
    return "neutral"


def _hair_presence_ratio(
    region: Any,
    hair_reference_region: Any,
    skin_reference_region: Any,
) -> float:
    if (
        region is None
        or getattr(region, "size", 0) == 0
        or cv2 is None
        or np is None
    ):
        return 0.0

    hair_h, hair_s, hair_v = _median_hsv(hair_reference_region)
    skin_h, skin_s, skin_v = _median_hsv(skin_reference_region)
    if hair_h is None or skin_h is None:
        return 0.0

    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    h = hsv[:, :, 0].astype(np.float32) * 2.0
    s = hsv[:, :, 1].astype(np.float32)
    v = hsv[:, :, 2].astype(np.float32)

    hair_score = (
        _hue_distance(h, hair_h) / 180.0
        + np.abs(s - hair_s) / 255.0
        + np.abs(v - hair_v) / 255.0
    )
    skin_score = (
        _hue_distance(h, skin_h) / 180.0
        + np.abs(s - skin_s) / 255.0
        + np.abs(v - skin_v) / 255.0
    )
    brightness_similarity_hair = np.abs(v - hair_v)
    brightness_similarity_skin = np.abs(v - skin_v)
    saturation_similarity_hair = np.abs(s - hair_s)
    saturation_similarity_skin = np.abs(s - skin_s)
    mask = (
        (
            (hair_score + 0.02 < skin_score)
            | (
                brightness_similarity_hair + saturation_similarity_hair + 8
                < brightness_similarity_skin + saturation_similarity_skin
            )
            | (
                (v <= skin_v - 10)
                & (_hue_distance(h, hair_h) <= 28)
                & (s >= max(10.0, float(hair_s) * 0.35))
            )
        )
        & (v >= max(18.0, float(hair_v) - 45.0))
        & (v <= min(250.0, float(hair_v) + 35.0))
        & (v <= 250)
    )
    return float(mask.mean())


def _hair_gray_percentage(region: Any) -> int:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return 0
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV).reshape(-1, 3)
    if hsv.size == 0:
        return 0
    s = hsv[:, 1].astype(np.float32)
    v = hsv[:, 2].astype(np.float32)
    ratio = float(((s <= 30) & (v >= 140)).mean())
    return int(round(ratio * 100))


def _hair_texture(region: Any) -> str:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return "straight"
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    edge_density = float((edges > 0).mean())
    if edge_density >= 0.16:
        return "curly"
    if edge_density >= 0.08:
        return "wavy"
    return "straight"


def _visibility_label(value: float) -> str:
    if value >= 0.66:
        return "true"
    if value >= 0.26:
        return "partially"
    return "false"


def _ear_angle_label(visibility: str, face_horizontal: str) -> str:
    if visibility == "false":
        return "back"
    if face_horizontal in {"wide", "narrow"}:
        return "profile"
    return "frontal"


def _ear_shape_label(face_shape: str, jawline_type: str) -> str:
    if face_shape == "round":
        return "round"
    if face_shape == "square" or jawline_type == "defined":
        return "rectangular"
    if face_shape == "heart":
        return "triangular"
    return "oval"


def _ear_lobe_attachment(visibility_ratio: float, jawline_type: str) -> str:
    if visibility_ratio < 0.3:
        return "attached"
    if jawline_type == "defined" and visibility_ratio < 0.52:
        return "mixed"
    return "free"


def _ear_lobe_size(area_ratio: float) -> str:
    if area_ratio >= 0.013:
        return "large"
    if area_ratio >= 0.008:
        return "medium"
    return "small"


def _ear_lobe_thickness(area_ratio: float) -> str:
    if area_ratio >= 0.012:
        return "thick"
    if area_ratio >= 0.007:
        return "medium"
    return "thin"


def _recommended_ear_closures(
    visibility_left: str,
    visibility_right: str,
    lobe_attachment: str,
    overall_scale: str,
) -> list[str]:
    closures = ["stud", "english_lock"]
    if visibility_left != "false" or visibility_right != "false":
        closures.append("french_hook")
    if lobe_attachment == "attached" or overall_scale == "delicate":
        closures = ["stud", "english_lock"]
    return closures


def _ear_weight_and_length(
    overall_scale: str,
    visibility_ratio: float,
    ears_covered: str,
) -> tuple[int, int, str]:
    max_weight = 8 if overall_scale == "delicate" else 12
    max_length = 32 if overall_scale == "delicate" else 42
    if visibility_ratio < 0.35 or ears_covered in {"both", "left", "right"}:
        max_weight -= 2
        max_length -= 8
    if max_weight <= 7:
        risk = "high"
    elif max_weight <= 10:
        risk = "medium"
    else:
        risk = "low"
    return max(max_weight, 4), max(max_length, 18), risk


def _neck_profile_label(neck_ratio: float, head_tilt_strong: bool) -> str:
    if head_tilt_strong:
        return "forward_head"
    if neck_ratio >= 1.5:
        return "straight"
    if neck_ratio <= 1.0:
        return "curved"
    return "straight"


def _collarbone_visibility(lower_space_ratio: float, neck_visibility: str) -> str:
    if neck_visibility == "hidden":
        return "hidden"
    if lower_space_ratio >= 0.32:
        return "high"
    if lower_space_ratio >= 0.2:
        return "medium"
    return "low"


def _necklace_recommendations_from_ratio(
    neck_ratio: float,
    neck_visibility: str,
    collarbone_visibility: str,
) -> tuple[list[str], str, str, str]:
    if neck_visibility == "hidden" or neck_ratio < 1.0:
        return ["matinee", "opera"], "high", "50-70", "yes"
    if neck_ratio > 1.5:
        return ["choker", "princess", "matinee"], "low", "35-50", "optional"
    if collarbone_visibility == "high":
        return ["princess", "matinee"], "low", "40-55", "optional"
    return ["princess", "matinee"], "medium", "45-60", "optional"


def _decollete_visibility(
    neck_visibility: str,
    lower_space_ratio: float,
    collarbone_visibility: str,
) -> str:
    if neck_visibility == "hidden" or lower_space_ratio < 0.1:
        return "covered"
    if collarbone_visibility == "high" or lower_space_ratio >= 0.28:
        return "full"
    return "partial"


def _collarbone_shape(
    collarbone_visibility: str,
    neck_base_type: str,
    overall_horizontal: str,
) -> str:
    if collarbone_visibility == "high" and neck_base_type == "narrow":
        return "prominent"
    if overall_horizontal == "wide":
        return "straight"
    return "curved"


def _chest_width_label(face_width_ratio: float) -> str:
    if face_width_ratio >= 0.44:
        return "broad"
    if face_width_ratio <= 0.34:
        return "narrow"
    return "medium"


def _decollete_recommendations(
    visibility: str,
    chest_width: str,
    collarbone_shape: str,
    neck_ratio: float,
) -> tuple[str, bool]:
    if visibility == "covered":
        return "45-60", False
    if neck_ratio >= 1.5 and chest_width != "broad":
        return "30-45", True
    if chest_width == "broad" or collarbone_shape == "straight":
        return "45-70", False
    if collarbone_shape == "prominent":
        return "35-55", True
    return "40-60", True


def _hue_contrast(hues: list[float]) -> str:
    if len(hues) < 2:
        return "monochromatic"
    diffs: list[float] = []
    for idx, a in enumerate(hues):
        for b in hues[idx + 1 :]:
            diff = abs(a - b)
            diffs.append(min(diff, 360.0 - diff))
    if not diffs:
        return "monochromatic"
    max_diff = max(diffs)
    if max_diff >= 145:
        return "complementary"
    if max_diff >= 95:
        return "triadic"
    if max_diff >= 28:
        return "analogous"
    return "monochromatic"


def _season_from_color_metrics(
    undertone: str,
    lightness: str,
    brightness_label: str,
    value_contrast: float,
    hue_contrast: str,
) -> tuple[str, str, str, str]:
    if undertone == "warm":
        if brightness_label == "clear" and lightness == "light":
            season = "spring"
            if value_contrast >= 0.5 or hue_contrast in {"triadic", "complementary"}:
                subtype = "bright_spring"
            elif value_contrast <= 0.18:
                subtype = "soft_spring"
            else:
                subtype = "true_spring"
        else:
            season = "autumn"
            subtype = "true_autumn" if value_contrast >= 0.42 else "soft_autumn"
    elif undertone == "cool":
        if brightness_label == "clear" or value_contrast >= 0.48:
            season = "winter"
            if value_contrast >= 0.62 or hue_contrast in {"triadic", "complementary"}:
                subtype = "bright_winter"
            elif lightness == "deep":
                subtype = "deep_winter"
            else:
                subtype = "true_winter"
        else:
            season = "summer"
            subtype = "soft_summer" if value_contrast <= 0.35 else "true_summer"
    else:
        if brightness_label == "clear" and value_contrast >= 0.5:
            season = "winter"
            subtype = "bright_winter"
        elif lightness == "light":
            season = "spring"
            subtype = "true_spring"
        else:
            season = "autumn"
            subtype = "soft_autumn"

    stone_intensity = (
        "deep" if value_contrast >= 0.7 else "saturated" if value_contrast >= 0.5 else "medium" if value_contrast >= 0.25 else "pastel"
    )
    contrast_style = (
        "dramatic" if value_contrast >= 0.7 else "high_contrast" if value_contrast >= 0.5 else "natural" if value_contrast >= 0.25 else "low_contrast"
    )
    return season, subtype, stone_intensity, contrast_style


def _recommended_stone_palette(
    season_type: str,
    undertone: str,
    stone_intensity: str,
) -> list[str]:
    intensity_base = {
        "pastel": ["pastel", "soft"],
        "medium": ["balanced", "soft"],
        "saturated": ["contrast", "saturated"],
        "deep": ["deep", "contrast"],
    }
    palette = list(intensity_base.get(stone_intensity, ["balanced", "soft"]))
    if season_type == "spring":
        palette.append("peach")
    elif season_type == "summer":
        palette.append("dusty_rose")
    elif season_type == "autumn":
        palette.append("olive")
    elif season_type == "winter":
        palette.append("berry")
    elif undertone == "warm":
        palette.append("champagne")
    elif undertone == "cool":
        palette.append("icy")
    return palette[:3]


def _skin_tone_depth(
    lightness: float | None,
    undertone: str,
) -> str:
    if lightness is None:
        return "medium"
    if lightness >= 82:
        return "very_light"
    if lightness >= 68:
        return "light"
    if undertone == "olive" and lightness >= 48:
        return "olive"
    if lightness >= 55:
        return "medium"
    if lightness >= 42:
        return "olive" if undertone in {"olive", "neutral"} else "tan"
    if lightness >= 30:
        return "tan"
    return "dark"


def _skin_evenness(region: Any) -> tuple[str, float]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return "slight_variation", 0.0
    lab = cv2.cvtColor(region, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    unevenness_score = (
        float(l_channel.std()) / 255.0 * 100.0 * 0.6
        + float(a_channel.std()) / 255.0 * 100.0 * 0.25
        + float(b_channel.std()) / 255.0 * 100.0 * 0.15
    )
    if unevenness_score < 5.8:
        return "uniform", round(unevenness_score, 3)
    if unevenness_score < 9.5:
        return "slight_variation", round(unevenness_score, 3)
    return "uneven", round(unevenness_score, 3)


def _skin_texture_primary(region: Any) -> tuple[str, float]:
    if region is None or getattr(region, "size", 0) == 0:
        return "smooth", 0.0
    texture_score = _laplacian_sharpness(region)
    if texture_score < 0.04:
        return "smooth", round(texture_score, 4)
    if texture_score < 0.08:
        return "fine_pores", round(texture_score, 4)
    if texture_score < 0.15:
        return "visible_pores", round(texture_score, 4)
    return "textured", round(texture_score, 4)


def _skin_shine_level(region: Any) -> tuple[str, float]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return "natural", 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    h = hsv[:, :, 0].astype(np.float32)
    s = hsv[:, :, 1].astype(np.float32)
    v = hsv[:, :, 2].astype(np.float32)
    highlight_ratio = float(((v >= 220) & (s <= 55)).mean())
    warm_glow_ratio = float(((h >= 10) & (h <= 26) & (v >= 178) & (s <= 110)).mean())
    shine_score = highlight_ratio + warm_glow_ratio * 0.1
    if shine_score >= 0.12:
        return "oily", round(shine_score, 4)
    if shine_score >= 0.055:
        return "dewy", round(shine_score, 4)
    if shine_score >= 0.03:
        return "natural", round(shine_score, 4)
    return "matte", round(shine_score, 4)


def _redness_areas(
    face_stats: dict[str, float | None],
    cheek_stats: dict[str, float | None],
    nose_stats: dict[str, float | None],
    chin_stats: dict[str, float | None],
) -> str:
    face_a = face_stats.get("a")
    if face_a is None:
        return "none"

    deltas = {
        "cheeks": max(
            (cheek_stats.get("a") or face_a) - face_a,
            0.0,
        ),
        "nose": max((nose_stats.get("a") or face_a) - face_a, 0.0),
        "chin": max((chin_stats.get("a") or face_a) - face_a, 0.0),
    }
    active = [name for name, delta in deltas.items() if delta >= 2.2]
    if face_a >= 20 and len(active) >= 2:
        return "whole_face"
    if not active:
        return "none"
    return max(active, key=lambda item: deltas[item])


def _fine_lines(region: Any, sharpness_score: float) -> str:
    if region is None or getattr(region, "size", 0) == 0:
        return "none"
    if sharpness_score < 0.06:
        return "none"
    texture_score = _laplacian_sharpness(region)
    if sharpness_score < 0.08 and texture_score < 0.09:
        return "none"
    if texture_score >= 0.2:
        return "under_eyes"
    if texture_score >= 0.15:
        return "forehead"
    if texture_score >= 0.11:
        return "around_mouth"
    return "none"


def _wrinkle_depth(
    texture_primary: str,
    fine_lines: str,
) -> str:
    if fine_lines == "none":
        return "none"
    if texture_primary in {"textured", "visible_pores"}:
        return "moderate"
    return "superficial"


def _freckles_level(region: Any) -> tuple[str, float]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return "none", 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV).reshape(-1, 3)
    if hsv.size == 0:
        return "none", 0.0
    h = hsv[:, 0].astype(np.float32) * 2.0
    s = hsv[:, 1].astype(np.float32)
    v = hsv[:, 2].astype(np.float32)
    freckles_ratio = float(
        (
            (h >= 14)
            & (h <= 34)
            & (s >= 35)
            & (s <= 140)
            & (v >= 65)
            & (v <= 165)
        ).mean()
    )
    if freckles_ratio >= 0.2:
        return "heavy", round(freckles_ratio, 4)
    if freckles_ratio >= 0.13:
        return "moderate", round(freckles_ratio, 4)
    if freckles_ratio >= 0.065:
        return "light", round(freckles_ratio, 4)
    return "none", round(freckles_ratio, 4)


def _moles_level(region: Any) -> tuple[str, float]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return "none", 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV).reshape(-1, 3)
    if hsv.size == 0:
        return "none", 0.0
    s = hsv[:, 1].astype(np.float32)
    v = hsv[:, 2].astype(np.float32)
    ratio = float(((v <= 85) & (s <= 120)).mean())
    if ratio >= 0.04:
        return "several", round(ratio, 4)
    if ratio >= 0.015:
        return "few", round(ratio, 4)
    return "none", round(ratio, 4)


def _recommended_metal_finish(
    undertone: str,
    skin_shine_level: str,
    freckles: str,
    skin_texture_primary: str,
) -> tuple[list[str], list[str]]:
    if skin_shine_level == "oily":
        recommended = ["satin", "matte", "brushed"]
        avoid = ["mirror"]
    elif skin_shine_level == "dewy":
        recommended = ["satin", "brushed", "mirror"]
        avoid = []
    elif undertone == "warm":
        recommended = ["mirror", "satin", "brushed"]
        avoid = []
    else:
        recommended = ["satin", "mirror", "brushed"]
        avoid = []

    if freckles in {"moderate", "heavy"}:
        recommended = ["satin", "brushed", "matte"]
        if "mirror" not in avoid:
            avoid.append("mirror")

    if skin_texture_primary == "textured" and "brushed" not in recommended:
        recommended.insert(0, "brushed")

    return recommended[:3], avoid


def _stone_cut_preference(
    skin_texture_primary: str,
    fine_lines: str,
    feature_scale: str,
    contrast_style: str,
) -> str:
    if fine_lines != "none" or skin_texture_primary in {"visible_pores", "textured"}:
        return "cabochon"
    if contrast_style in {"high_contrast", "dramatic"}:
        return "princess"
    if feature_scale == "large":
        return "rose"
    return "brilliant"


def _facial_thirds_ratio(
    y_min: int,
    brow_y: float,
    nose_base_y: float,
    y_max: int,
    face_h: int,
) -> tuple[dict[str, float], float]:
    upper = _clamp(_safe_ratio(brow_y - y_min, face_h), 0.0, 1.0)
    middle = _clamp(_safe_ratio(nose_base_y - brow_y, face_h), 0.0, 1.0)
    lower = _clamp(_safe_ratio(y_max - nose_base_y, face_h), 0.0, 1.0)
    target = 1.0 / 3.0
    deviation = (
        ((upper - target) ** 2 + (middle - target) ** 2 + (lower - target) ** 2) / 3.0
    ) ** 0.5
    return (
        {
            "upper": round(upper, 3),
            "middle": round(middle, 3),
            "lower": round(lower, 3),
        },
        round(deviation, 3),
    )


def _golden_ratio_deviation(
    face_ratio: float,
    mouth_to_nose_ratio: float,
    thirds_deviation: float,
) -> float:
    face_dev = abs(face_ratio - 1.618) / 1.618
    mouth_nose_dev = abs(mouth_to_nose_ratio - 1.618) / 1.618
    deviation = ((face_dev**2 + mouth_nose_dev**2 + thirds_deviation**2) / 3.0) ** 0.5
    return round(deviation, 3)


def _harmony_level(
    golden_ratio_deviation: float,
    eye_spacing_deviation: float,
    center_alignment_deviation: float,
) -> str:
    if (
        golden_ratio_deviation <= 0.14
        and eye_spacing_deviation <= 0.14
        and center_alignment_deviation <= 0.05
    ):
        return "classic"
    if (
        golden_ratio_deviation <= 0.24
        and eye_spacing_deviation <= 0.22
        and center_alignment_deviation <= 0.11
    ):
        return "character"
    if (
        golden_ratio_deviation <= 0.38
        and eye_spacing_deviation <= 0.32
        and center_alignment_deviation <= 0.12
    ):
        return "expressive"
    return "avantgarde"


def _symmetry_guidance(harmony_level: str) -> tuple[str, str]:
    if harmony_level == "classic":
        return "critical", "strict"
    if harmony_level == "character":
        return "important", "balanced"
    if harmony_level == "expressive":
        return "flexible", "asymmetric_possible"
    return "flexible", "asymmetric_possible"


def _vibe_analysis(
    line_type: str,
    harmony_level: str,
    contrast_style: str,
    undertone: str,
    overall_scale: str,
    head_tilt_strong: bool,
    face_shape: str,
) -> dict[str, Any]:
    if contrast_style in {"high_contrast", "dramatic"}:
        primary_impression = "bold"
    elif line_type == "graphic":
        primary_impression = "mysterious"
    elif undertone == "warm" and harmony_level in {"classic", "character"}:
        primary_impression = "elegant"
    elif face_shape in {"round", "oval"}:
        primary_impression = "romantic"
    else:
        primary_impression = "sweet"

    face_expression = "serious" if head_tilt_strong or line_type == "graphic" else "neutral_pleasant"
    energy_level = (
        "dynamic"
        if contrast_style == "dramatic"
        else "balanced"
        if harmony_level in {"character", "expressive"}
        else "calm"
    )

    recommended_mood = "_".join(
        part
        for part in [
            primary_impression,
            "warm" if undertone == "warm" else "cool" if undertone == "cool" else "balanced",
        ]
        if part
    )

    forbidden: list[str] = []
    if primary_impression in {"elegant", "romantic"}:
        forbidden.extend(["aggressive", "edgy"])
    if overall_scale != "expressive":
        forbidden.append("overly_cute")
    if harmony_level == "classic":
        forbidden.append("chaotic")

    return {
        "analysisConfidence": "heuristic_style_v1",
        "primaryImpression": primary_impression,
        "faceExpressionBaseline": face_expression,
        "energyLevel": energy_level,
        "recommendedJewelryMood": recommended_mood,
        "forbiddenJewelryMood": forbidden,
    }


def _avoid_rules(
    recommended_metal: str,
    overall_scale: str,
    line_type: str,
    hair_analysis: dict[str, Any],
    color_contrast_analysis: dict[str, Any],
    skin_analysis: dict[str, Any],
    facial_harmony_analysis: dict[str, Any],
    neck_analysis: dict[str, Any],
) -> dict[str, Any]:
    metal_forbidden: list[str] = []
    if recommended_metal == "gold":
        metal_forbidden.extend(["silver", "platinum"])
    elif recommended_metal == "silver":
        metal_forbidden.extend(["yellow_gold", "rose_gold"])

    shape_forbidden: list[str] = []
    geometric_forbidden: list[str] = []
    length_forbidden: list[str] = []
    scale_forbidden: list[str] = []
    texture_forbidden: list[str] = []
    finish_forbidden: list[str] = []
    stone_forbidden: list[str] = []
    stone_color_forbidden: list[str] = []
    weight_forbidden: list[str] = []

    ears_covered = str(hair_analysis.get("earsCovered") or "none")
    hair_volume = str(hair_analysis.get("hairVolume") or "medium")
    contrast_style = str(color_contrast_analysis.get("recommendedContrastStyle") or "natural")
    skin_shine_level = str(skin_analysis.get("skinShineLevel") or "natural")
    skin_texture_primary = str(skin_analysis.get("skinTexturePrimary") or "smooth")
    fine_lines = str(skin_analysis.get("fineLines") or "none")
    avoid_metal_finish = skin_analysis.get("avoidMetalFinish") or []
    harmony_level = str(facial_harmony_analysis.get("harmonyLevel") or "character")
    symmetry_mode = str(facial_harmony_analysis.get("recommendedSymmetry") or "balanced")
    rigid_choker_risk = str(neck_analysis.get("rigidChokerRisk") or "medium")

    if overall_scale == "delicate":
        scale_forbidden.extend(["oversized"])
        weight_forbidden.append("heavy_drop")
        length_forbidden.append("longer_than_50mm")
    if hair_volume == "high":
        scale_forbidden.append("miniature")
    if ears_covered in {"both", "left", "right"}:
        length_forbidden.append("too_hidden_by_hair")
        shape_forbidden.append("oversized_hoops")
        geometric_forbidden.append("sharp_dangles")
    if line_type == "soft_geometric":
        geometric_forbidden.append("chunky_geometric")
    if contrast_style == "low_contrast":
        stone_color_forbidden.extend(["icy_white", "cold_blue"])
        stone_forbidden.extend(["deep_black", "high_contrast_gems"])
    if recommended_metal == "gold":
        finish_forbidden.append("oxidized")
    if skin_shine_level == "oily":
        finish_forbidden.append("mirror")
        texture_forbidden.append("highly_textured_rough")
    if skin_texture_primary in {"visible_pores", "textured"} or fine_lines != "none":
        scale_forbidden.append("oversized")
        stone_forbidden.append("oversized_brilliant")
    if rigid_choker_risk == "high":
        length_forbidden.append("short_choker")
    if harmony_level == "classic":
        shape_forbidden.append("chaotic_asymmetry")
    elif harmony_level == "character":
        shape_forbidden.append("extreme_asymmetry")
    if symmetry_mode == "strict":
        geometric_forbidden.append("mismatched_pair")
    texture_forbidden.append("heavy_hammered")

    return {
        "geometricForbidden": geometric_forbidden,
        "shapeForbidden": shape_forbidden,
        "lengthForbidden": length_forbidden,
        "metalForbidden": metal_forbidden,
        "stoneForbidden": stone_forbidden,
        "stoneColorForbidden": stone_color_forbidden,
        "textureForbidden": texture_forbidden,
        "finishForbidden": finish_forbidden + [item for item in avoid_metal_finish if item not in finish_forbidden],
        "scaleForbidden": scale_forbidden,
        "weightForbidden": weight_forbidden,
        "occasionBased": {
            "business": ["chandelier", "noisy", "long_dangle"],
            "evening": ["too_tiny"] if hair_volume == "high" else ["plastic"],
        },
    }


def _lab_color_stats(region: Any) -> dict[str, Any]:
    if region is None or getattr(region, "size", 0) == 0 or cv2 is None or np is None:
        return {
            "skinUndertone": "neutral",
            "appearanceLightness": "medium",
            "contrastLevel": "medium",
            "appearanceBrightness": "soft",
            "recommendedMetal": "mixed",
            "recommendedMetals": ["silver", "mixed"],
            "recommendedStonePalette": ["soft", "contrast"],
            "metrics": {},
        }

    lab = cv2.cvtColor(region, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    l_mean = float(l_channel.mean())
    a_mean = float(a_channel.mean()) - 128.0
    b_mean = float(b_channel.mean()) - 128.0

    appearance_lightness = (
        "light" if l_mean >= 170 else "medium" if l_mean >= 105 else "deep"
    )

    if b_mean >= 7:
        undertone = "warm"
    elif b_mean <= -5:
        undertone = "cool"
    else:
        undertone = "neutral"

    region_contrast = _variance_contrast(region)
    contrast_level = (
        "high" if region_contrast >= 0.55 else "medium" if region_contrast >= 0.28 else "low"
    )
    appearance_brightness = "clear" if l_mean >= 175 else "soft"
    recommended_metal, recommended_metals = _determine_metal(
        _clamp(l_mean / 255.0, 0.0, 1.0),
        _clamp((b_mean + 32.0) / 64.0, 0.0, 1.0),
    )

    if recommended_metal == "gold":
        palette = ["deep", "contrast"]
    elif recommended_metal == "silver":
        palette = ["light", "soft"]
    else:
        palette = ["soft", "contrast"]

    return {
        "skinUndertone": undertone,
        "appearanceLightness": appearance_lightness,
        "contrastLevel": contrast_level,
        "appearanceBrightness": appearance_brightness,
        "recommendedMetal": recommended_metal,
        "recommendedMetals": recommended_metals,
        "recommendedStonePalette": palette,
        "metrics": {
            "labLightness": round(l_mean, 3),
            "labA": round(a_mean, 3),
            "labB": round(b_mean, 3),
        },
    }


def _face_shape(
    face_ratio: float,
    jaw_to_cheek: float,
) -> str:
    if face_ratio >= 1.34:
        return "elongated"
    if face_ratio <= 0.96:
        return "round"
    if jaw_to_cheek >= 0.94 and face_ratio <= 1.15:
        return "square"
    return "oval"


def _recommended_shapes_from_face(
    face_shape: str,
    line_type: str,
) -> list[str]:
    if face_shape in {"round", "square"}:
        return ["elongated", "drop", "clean_line"]
    if line_type == "graphic":
        return ["clean_line", "geometry", "elongated"]
    return ["oval", "drop", "soft_geometry", "clean_line"]


def _user_summary(
    scale: str,
    shapes: list[str],
    metal: str,
) -> tuple[str, list[str]]:
    scale_text = "деликатного масштаба" if scale == "delicate" else "среднего масштаба"
    shape_text = (
        "мягкой геометрии"
        if any(item in {"oval", "drop", "soft_geometry"} for item in shapes)
        else "чистой графики"
    )
    metal_text = (
        "теплого сияния"
        if metal == "gold"
        else "деликатного блеска"
        if metal == "silver"
        else "спокойного блеска"
    )
    summary = (
        f"Вам подойдут украшения {scale_text}, {shape_text} и {metal_text}. "
        "Они поддержат линии лица и не перегрузят образ."
    )
    bullets = [
        "Серьги средней длины помогут сохранить баланс у лица.",
        "Вытянутые или мягко-овальные формы будут смотреться гармоничнее.",
        "Лучше выбирать деликатный блеск без лишней тяжести.",
    ]
    return summary, bullets


def _primary_zone(
    overall_vertical: str,
    neck_visibility: str,
) -> tuple[str, str]:
    if neck_visibility == "visible" and overall_vertical == "compact":
        return "necklace", "зоне шеи"
    return "earrings", "зоне лица"


def _user_summary_v2(
    scale: str,
    shapes: list[str],
    metal: str,
    primary_zone_text: str,
    neck_visibility: str,
) -> tuple[str, list[str]]:
    scale_text = "деликатного масштаба" if scale == "delicate" else "среднего масштаба"
    if any(item in {"oval", "drop", "soft_geometry"} for item in shapes):
        shape_text = "мягкой геометрии"
    elif any(item in {"clean_line", "geometry", "elongated"} for item in shapes):
        shape_text = "чистой вытянутой графики"
    else:
        shape_text = "спокойной формы"

    metal_text = (
        "теплых металлах"
        if metal == "gold"
        else "холодных металлах"
        if metal == "silver"
        else "смешанных металлах"
    )

    summary = (
        f"Вам подойдут украшения {scale_text}, {shape_text} и спокойного блеска. "
        f"Лучше сделать акцент в {primary_zone_text}, а смотреться гармоничнее они будут в {metal_text}."
    )

    bullets = [
        "Лучше выбирать формы без лишней тяжести и визуального перегруза.",
        "Мягкие вытянутые линии помогут сохранить баланс у лица.",
    ]
    if neck_visibility != "hidden":
        bullets.append("Колье средней длины поддержит образ и не утяжелит линию шеи.")
    else:
        bullets.append("Основной акцент лучше оставить у лица, без сложного многослойного колье.")
    return summary, bullets


def _detect_with_mediapipe(image_rgb: Any) -> tuple[list[list[tuple[int, int]]], list[str]]:
    if mp_solutions is None or np is None:
        return [], ["MediaPipe unavailable"]

    height, width = image_rgb.shape[:2]
    with mp_solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=2,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(image_rgb)

    faces = []
    for face_landmarks in results.multi_face_landmarks or []:
        points = []
        for landmark in face_landmarks.landmark:
            points.append(
                (
                    int(_clamp(landmark.x, 0.0, 1.0) * (width - 1)),
                    int(_clamp(landmark.y, 0.0, 1.0) * (height - 1)),
                )
            )
        faces.append(points)
    return faces, []


def _build_baseline_analysis(
    photo_data: bytes,
    filename: str | None = None,
) -> dict[str, Any]:
    image = Image.open(BytesIO(photo_data)).convert("RGB")
    width, height = image.size
    stat = ImageStat.Stat(image)

    mean_r, mean_g, mean_b = stat.mean
    brightness_raw = (mean_r + mean_g + mean_b) / (255 * 3)
    brightness = _clamp(brightness_raw, 0.0, 1.0)

    contrast_raw = sum(stat.stddev) / (255 * 3)
    contrast = _clamp(contrast_raw * 3.0, 0.0, 1.0)

    warmth = _clamp((mean_r + mean_g * 0.35 - mean_b * 0.85) / 255, 0.0, 1.0)
    aspect_ratio = height / max(width, 1)

    light_quality = _quality_bucket(brightness, 0.26, 0.5)
    sharpness = _quality_bucket(contrast, 0.12, 0.24)
    can_continue = width >= 512 and height >= 512 and light_quality != "poor"

    recommended_metal, recommended_metals = _determine_metal(brightness, warmth)
    recommended_shapes = _recommended_shapes(aspect_ratio)
    scale = _appearance_scale(width, height)
    earring_length = ["short", "medium"] if aspect_ratio <= 1.2 else ["medium"]
    primary_category, primary_zone_text = _primary_zone("balanced", "partial")
    summary, bullets = _user_summary_v2(
        scale,
        recommended_shapes,
        recommended_metal,
        primary_zone_text,
        "partial",
    )

    if recommended_metal == "gold":
        stone_palette = ["deep", "contrast"]
    elif recommended_metal == "silver":
        stone_palette = ["light", "soft"]
    else:
        stone_palette = ["soft", "contrast"]

    photo_quality = {
        "faceDetected": True,
        "singlePerson": True,
        "faceVisibleLarge": width >= 512 and height >= 512,
        "sharpness": sharpness,
        "lightQuality": light_quality,
        "filterDetected": False,
        "headTiltStrong": False,
        "earVisible": "partial",
        "neckVisible": "partial",
    }
    retry_hint = None if can_continue else _quality_retry_hint(photo_quality)

    return {
        "success": True,
        "can_continue": can_continue,
        "quality_status": "ok" if can_continue else "retry_required",
        "retry_hint": retry_hint,
        "analysis": {
            "version": "1.0",
            "photoQuality": photo_quality,
            "faceGeometry": {
                "faceShape": "oval" if aspect_ratio >= 1.05 else "round",
                "faceLength": "long" if aspect_ratio >= 1.28 else "balanced",
                "faceWidth": "wide" if aspect_ratio <= 0.9 else "balanced",
                "jawlineType": "soft",
                "cheekboneProminence": "medium",
                "chinType": "soft",
                "foreheadProportion": "balanced",
                "overallVertical": "elongated" if aspect_ratio >= 1.2 else "balanced",
                "overallHorizontal": "balanced",
            },
            "appearanceScale": {
                "overallAppearanceScale": scale,
                "featureScale": "medium",
                "eyeScale": "medium",
                "lipScale": "medium",
                "noseScale": "medium",
                "featureDensity": "medium",
                "allowedJewelryScale": "medium" if scale != "delicate" else "mini",
                "riskOfOverload": "medium" if scale != "delicate" else "high",
            },
            "lineAnalysis": {
                "lineType": "soft_geometric" if aspect_ratio >= 0.95 else "graphic",
                "dominantLineDirection": "elongated" if aspect_ratio >= 1.2 else "rounded",
                "softnessLevel": "medium",
                "graphicLevel": "medium",
                "visualStrictness": "balanced",
                "visualNaturalness": "medium",
            },
            "colorAnalysis": {
                "eyeColor": "unknown",
                "hairColor": "unknown",
                "hairDepth": "medium",
                "skinUndertone": (
                    "warm" if recommended_metal == "gold" else "cool" if recommended_metal == "silver" else "neutral"
                ),
                "appearanceLightness": "light" if brightness >= 0.68 else "medium" if brightness >= 0.4 else "deep",
                "contrastLevel": "high" if contrast >= 0.6 else "medium" if contrast >= 0.3 else "low",
                "appearanceBrightness": "clear" if brightness >= 0.7 else "soft",
                "recommendedMetal": recommended_metal,
                "recommendedStonePalette": stone_palette,
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
                "primaryCategory": primary_category,
                "recommendedCategories": ["earrings", "necklace", "rings"],
                "recommendedScale": "medium" if scale != "delicate" else "mini",
                "recommendedEarringLength": earring_length,
                "recommendedEarringWeight": "light_medium",
                "recommendedNecklaceLength": ["short", "medium"],
                "recommendedShapes": recommended_shapes,
                "recommendedTextures": ["smooth", "mirror"],
                "recommendedMetals": recommended_metals,
                "avoidAsPrimary": ["too_heavy", "too_tiny"],
                "stylistSummaryInternal": summary,
                "metal_colors": recommended_metals,
                "stone_colors": stone_palette,
                "styles": ["элегантный", "спокойный"],
            },
            "userFacing": {
                "summary": summary,
                "bullets": bullets,
            },
            "debug": {
                "pipelineVersion": "baseline-cpu-v1",
                "provider": "ml-service",
                "filename": filename,
                "imageSize": {"width": width, "height": height},
                "metrics": {
                    "brightness": round(brightness, 4),
                    "contrast": round(contrast, 4),
                    "warmth": round(warmth, 4),
                    "aspectRatio": round(aspect_ratio, 4),
                },
                "limitations": [
                    "Face geometry is estimated from the full image",
                    "No hair segmentation yet",
                ],
            },
        },
    }


def _build_mediapipe_analysis(
    image_rgb: Any,
    filename: str | None = None,
) -> dict[str, Any]:
    height, width = image_rgb.shape[:2]
    faces, warnings = _detect_with_mediapipe(image_rgb)

    if not faces:
        baseline = _build_baseline_analysis(
            _image_bytes_from_rgb(image_rgb),
            filename=filename,
        )
        baseline["success"] = True
        baseline["can_continue"] = False
        baseline["quality_status"] = "retry_required"
        baseline["analysis"]["photoQuality"]["faceDetected"] = False
        baseline["analysis"]["photoQuality"]["faceVisibleLarge"] = False
        baseline["analysis"]["photoQuality"]["singlePerson"] = len(faces) == 1
        baseline["retry_hint"] = _quality_retry_hint(
            baseline["analysis"]["photoQuality"]
        )
        baseline["analysis"]["debug"]["pipelineVersion"] = "mediapipe-fallback-v1"
        baseline["analysis"]["debug"]["limitations"] = warnings + [
            "Face mesh did not detect a face",
        ]
        return baseline

    single_person = len(faces) == 1
    landmarks = faces[0]
    xs = [x for x, _ in landmarks]
    ys = [y for _, y in landmarks]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    face_w = max(1, x_max - x_min)
    face_h = max(1, y_max - y_min)
    face_area_ratio = (face_w * face_h) / float(width * height)
    face_visible_large = face_area_ratio >= 0.08 and face_w >= width * 0.24

    face_roi = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.12),
        int(y_min + face_h * 0.1),
        int(x_max - face_w * 0.12),
        int(y_max - face_h * 0.18),
    )
    hair_roi = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.12),
        max(0, int(y_min - face_h * 0.22)),
        int(x_max - face_w * 0.12),
        int(y_min + face_h * 0.06),
    )

    left_eye = _crop_np(
        image_rgb,
        min(_px(landmarks, LEFT_EYE_OUTER)[0], _px(landmarks, LEFT_EYE_INNER)[0]) - 8,
        min(_px(landmarks, LEFT_EYE_UPPER)[1], _px(landmarks, LEFT_EYE_LOWER)[1]) - 8,
        max(_px(landmarks, LEFT_EYE_OUTER)[0], _px(landmarks, LEFT_EYE_INNER)[0]) + 8,
        max(_px(landmarks, LEFT_EYE_UPPER)[1], _px(landmarks, LEFT_EYE_LOWER)[1]) + 8,
    )
    right_eye = _crop_np(
        image_rgb,
        min(_px(landmarks, RIGHT_EYE_INNER)[0], _px(landmarks, RIGHT_EYE_OUTER)[0]) - 8,
        min(_px(landmarks, RIGHT_EYE_UPPER)[1], _px(landmarks, RIGHT_EYE_LOWER)[1]) - 8,
        max(_px(landmarks, RIGHT_EYE_INNER)[0], _px(landmarks, RIGHT_EYE_OUTER)[0]) + 8,
        max(_px(landmarks, RIGHT_EYE_UPPER)[1], _px(landmarks, RIGHT_EYE_LOWER)[1]) + 8,
    )
    eye_roi = _concat_regions_horizontally(left_eye, right_eye)

    face_mean = _mean_rgb(face_roi)
    face_brightness = _rgb_brightness(face_mean)
    light_quality = _quality_bucket(face_brightness, 0.22, 0.42)
    sharpness_score = _laplacian_sharpness(face_roi)
    # Mobile portraits with soft skin areas or partially uniform face regions
    # produce much lower Laplacian scores than studio/reference shots.
    # Keep "poor" only for clearly blurred frames and treat low-but-usable
    # handheld photos as "medium" so the flow can continue.
    sharpness = _quality_bucket(sharpness_score, 0.03, 0.18)

    left_eye_outer = _px(landmarks, LEFT_EYE_OUTER)
    right_eye_outer = _px(landmarks, RIGHT_EYE_OUTER)
    eye_slope = abs(right_eye_outer[1] - left_eye_outer[1]) / max(
        1.0, _distance(left_eye_outer, right_eye_outer)
    )
    head_tilt_strong = eye_slope >= 0.11

    jaw_w = _distance(_px(landmarks, LEFT_JAW), _px(landmarks, RIGHT_JAW))
    cheek_w = _distance(_px(landmarks, LEFT_CHEEK), _px(landmarks, RIGHT_CHEEK))
    eye_w = _distance(_px(landmarks, LEFT_EYE_OUTER), _px(landmarks, RIGHT_EYE_OUTER))
    left_eye_width = _distance(_px(landmarks, LEFT_EYE_OUTER), _px(landmarks, LEFT_EYE_INNER))
    right_eye_width = _distance(_px(landmarks, RIGHT_EYE_OUTER), _px(landmarks, RIGHT_EYE_INNER))
    mouth_w = _distance(_px(landmarks, MOUTH_LEFT), _px(landmarks, MOUTH_RIGHT))
    nose_w = _distance(_px(landmarks, NOSE_LEFT), _px(landmarks, NOSE_RIGHT))
    face_ratio = face_h / max(face_w, 1)
    jaw_to_cheek = jaw_w / max(cheek_w, 1)
    face_shape = _face_shape(face_ratio, jaw_to_cheek)
    face_length = "long" if face_ratio >= 1.3 else "short" if face_ratio <= 0.92 else "balanced"
    face_width = "narrow" if face_ratio >= 1.28 else "wide" if face_ratio <= 0.95 else "balanced"
    overall_vertical = "elongated" if face_ratio >= 1.2 else "compact" if face_ratio <= 0.92 else "balanced"
    overall_horizontal = "wide" if face_width == "wide" else "narrow" if face_width == "narrow" else "balanced"

    overall_scale = (
        "delicate"
        if face_area_ratio < 0.09
        else "expressive"
        if face_area_ratio > 0.18
        else "medium"
    )
    feature_density_ratio = (eye_w + mouth_w + nose_w) / max(face_w, 1)
    feature_density = (
        "dense" if feature_density_ratio >= 0.82 else "light" if feature_density_ratio <= 0.58 else "medium"
    )
    line_type = "graphic" if jaw_to_cheek >= 0.94 and face_shape in {"square"} else "soft_geometric"

    brow_y = (
        _px(landmarks, LEFT_BROW_UPPER)[1] + _px(landmarks, RIGHT_BROW_UPPER)[1]
    ) / 2.0
    nose_base_point = _px(landmarks, NOSE_BASE)
    nose_base_y = float(nose_base_point[1])
    mouth_center_x = (_px(landmarks, MOUTH_LEFT)[0] + _px(landmarks, MOUTH_RIGHT)[0]) / 2.0
    mouth_center_y = (
        _px(landmarks, UPPER_LIP)[1]
        + _px(landmarks, MOUTH_LEFT)[1]
        + _px(landmarks, MOUTH_RIGHT)[1]
    ) / 3.0
    face_center_x = (x_min + x_max) / 2.0
    average_eye_width = (left_eye_width + right_eye_width) / 2.0
    eye_gap = _distance(_px(landmarks, LEFT_EYE_INNER), _px(landmarks, RIGHT_EYE_INNER))
    eye_spacing_deviation = round(
        abs(_safe_ratio(eye_gap, max(average_eye_width, 1.0), 1.0) - 1.0),
        3,
    )
    nose_to_mouth_ratio = round(
        _safe_ratio(mouth_center_y - nose_base_y, face_h),
        3,
    )
    facial_third_ratio, thirds_deviation = _facial_thirds_ratio(
        y_min,
        brow_y,
        nose_base_y,
        y_max,
        face_h,
    )
    mouth_to_nose_ratio = _safe_ratio(mouth_w, max(nose_w, 1.0), 1.618)
    golden_ratio_deviation = _golden_ratio_deviation(
        face_ratio,
        mouth_to_nose_ratio,
        thirds_deviation,
    )
    eye_balance_deviation = abs(
        _safe_ratio(face_center_x - _px(landmarks, LEFT_EYE_OUTER)[0], face_w)
        - _safe_ratio(_px(landmarks, RIGHT_EYE_OUTER)[0] - face_center_x, face_w)
    )
    nose_center_x = (_px(landmarks, NOSE_LEFT)[0] + _px(landmarks, NOSE_RIGHT)[0]) / 2.0
    center_alignment_deviation = round(
        (
            abs(nose_center_x - face_center_x) / max(face_w, 1.0)
            + abs(mouth_center_x - face_center_x) / max(face_w, 1.0)
            + eye_balance_deviation
        )
        / 3.0,
        3,
    )
    harmony_level = _harmony_level(
        golden_ratio_deviation,
        eye_spacing_deviation,
        center_alignment_deviation,
    )
    symmetry_importance, recommended_symmetry = _symmetry_guidance(harmony_level)
    facial_harmony_analysis = {
        "analysisConfidence": "heuristic_landmarks_v1",
        "facialThirdRatio": facial_third_ratio,
        "eyeSpacingDeviation": eye_spacing_deviation,
        "noseToMouthRatio": nose_to_mouth_ratio,
        "goldenRatioDeviation": golden_ratio_deviation,
        "centerAlignmentDeviation": center_alignment_deviation,
        "harmonyLevel": harmony_level,
        "symmetryImportance": symmetry_importance,
        "recommendedSymmetry": recommended_symmetry,
    }
    vibe_analysis = _vibe_analysis(
        line_type,
        harmony_level,
        contrast_style="natural",
        undertone="neutral",
        overall_scale=overall_scale,
        head_tilt_strong=head_tilt_strong,
        face_shape=face_shape,
    )

    color_stats = _lab_color_stats(face_roi)
    hair_color, hair_depth = _classify_hair_color(hair_roi)
    eye_color = _classify_eye_color(eye_roi)
    hair_color_secondary = _hair_secondary_tone(hair_roi)
    recommended_shapes = _recommended_shapes_from_face(face_shape, line_type)
    recommended_scale = "mini" if overall_scale == "delicate" else "medium"
    earring_length = ["medium"] if overall_vertical == "elongated" else ["short", "medium"]

    ear_visibility = "both"
    if x_min <= width * 0.06 or x_max >= width * 0.94:
        ear_visibility = "partial"

    left_hair_side = _crop_np(
        image_rgb,
        int(x_min - face_w * 0.06),
        int(y_min + face_h * 0.24),
        int(x_min + face_w * 0.03),
        int(y_min + face_h * 0.58),
    )
    right_hair_side = _crop_np(
        image_rgb,
        int(x_max - face_w * 0.03),
        int(y_min + face_h * 0.24),
        int(x_max + face_w * 0.06),
        int(y_min + face_h * 0.58),
    )
    forehead_band = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.24),
        int(y_min),
        int(x_max - face_w * 0.24),
        int(y_min + face_h * 0.14),
    )
    lower_left_hair = _crop_np(
        image_rgb,
        int(x_min - face_w * 0.08),
        int(y_max + face_h * 0.02),
        int(x_min + face_w * 0.04),
        int(y_max + face_h * 0.18),
    )
    lower_right_hair = _crop_np(
        image_rgb,
        int(x_max - face_w * 0.04),
        int(y_max + face_h * 0.02),
        int(x_max + face_w * 0.08),
        int(y_max + face_h * 0.18),
    )

    left_cover_ratio = _hair_presence_ratio(left_hair_side, hair_roi, face_roi)
    right_cover_ratio = _hair_presence_ratio(right_hair_side, hair_roi, face_roi)
    lower_cover_ratio = max(
        _hair_presence_ratio(lower_left_hair, hair_roi, face_roi),
        _hair_presence_ratio(lower_right_hair, hair_roi, face_roi),
    )
    top_hair_ratio = (
        0.85
        if hair_color != "unknown" and hair_roi is not None and getattr(hair_roi, "size", 0) > 0
        else _hair_presence_ratio(hair_roi, hair_roi, face_roi)
    )
    forehead_cover_ratio = _hair_presence_ratio(forehead_band, hair_roi, face_roi)

    if left_cover_ratio >= 0.45 and right_cover_ratio >= 0.45:
        ears_covered = "both"
    elif left_cover_ratio >= 0.32:
        ears_covered = "left"
    elif right_cover_ratio >= 0.32:
        ears_covered = "right"
    else:
        ears_covered = "none"

    forehead_covered = (
        "full"
        if forehead_cover_ratio >= 0.24
        else "partially"
        if forehead_cover_ratio >= 0.1
        else "none"
    )
    hair_length = (
        "very_long"
        if lower_cover_ratio >= 0.42
        else "long"
        if lower_cover_ratio >= 0.26
        else "medium"
        if lower_cover_ratio >= 0.12
        else "short"
    )
    hair_volume = (
        "high"
        if max(top_hair_ratio, left_cover_ratio, right_cover_ratio) >= 0.55
        else "medium"
        if max(top_hair_ratio, left_cover_ratio, right_cover_ratio) >= 0.24
        else "low"
    )
    hair_texture = _hair_texture(hair_roi)
    _, _, root_val = _median_hsv(forehead_band)
    _, _, hair_val = _median_hsv(hair_roi)
    hair_roots_visible = bool(
        root_val is not None
        and hair_val is not None
        and root_val + 14 < hair_val
    )
    hair_gray_percentage = _hair_gray_percentage(hair_roi)

    face_lab_stats = _region_lab_stats(face_roi)
    skin_lightness = face_lab_stats["lightness"]
    hair_lightness = _region_lab_lightness(hair_roi)
    eye_lightness = _region_lab_lightness(eye_roi)
    value_contrast = (
        round(abs((hair_lightness or 0.0) - (skin_lightness or 0.0)) / 100.0, 3)
        if skin_lightness is not None and hair_lightness is not None
        else 0.0
    )
    formula_contrast_level = (
        "high" if value_contrast > 0.5 else "medium" if value_contrast >= 0.2 else "low"
    )
    skin_hue, _, _ = _median_hsv(face_roi)
    hair_hue, _, _ = _median_hsv(hair_roi)
    eye_hue, _, _ = _median_hsv(eye_roi)
    valid_hues = [value for value in [skin_hue, hair_hue, eye_hue] if value is not None]
    hue_contrast = _hue_contrast(valid_hues)
    season_type, color_subtype, stone_intensity, contrast_style = _season_from_color_metrics(
        color_stats["skinUndertone"],
        color_stats["appearanceLightness"],
        color_stats["appearanceBrightness"],
        value_contrast,
        hue_contrast,
    )
    vibe_analysis = _vibe_analysis(
        line_type,
        harmony_level,
        contrast_style,
        color_stats["skinUndertone"],
        overall_scale,
        head_tilt_strong,
        face_shape,
    )
    recommended_stone_palette = _recommended_stone_palette(
        season_type,
        color_stats["skinUndertone"],
        stone_intensity,
    )
    hair_analysis = {
        "segmentationAvailable": True,
        "segmentationMask": True,
        "segmentationMethod": "heuristic_head_mask_v1",
        "analysisConfidence": "heuristic",
        "hairLength": hair_length,
        "hairVolume": hair_volume,
        "hairTexture": hair_texture,
        "earsCovered": ears_covered,
        "foreheadCovered": forehead_covered,
        "hairColorPrimary": hair_color,
        "hairColorSecondary": hair_color_secondary,
        "hairRootsVisible": hair_roots_visible,
        "hairGrayPercentage": hair_gray_percentage,
        "coverageRatios": {
            "top": round(top_hair_ratio, 3),
            "leftSide": round(left_cover_ratio, 3),
            "rightSide": round(right_cover_ratio, 3),
            "forehead": round(forehead_cover_ratio, 3),
            "lower": round(lower_cover_ratio, 3),
        },
    }
    color_contrast_analysis = {
        "analysisConfidence": "formula_plus_heuristic",
        "skinLightness": skin_lightness,
        "hairLightness": hair_lightness,
        "eyeLightness": eye_lightness,
        "valueContrast": value_contrast,
        "valueContrastBand": formula_contrast_level,
        "skinHue": round(skin_hue, 2) if skin_hue is not None else None,
        "hairHue": round(hair_hue, 2) if hair_hue is not None else None,
        "eyeHue": round(eye_hue, 2) if eye_hue is not None else None,
        "hueContrast": hue_contrast,
        "colorSeasonType": season_type,
        "colorSubtype": color_subtype,
        "recommendedStoneIntensity": stone_intensity,
        "recommendedContrastStyle": contrast_style,
        "recommendedStonePalette": recommended_stone_palette,
        "evidence": {
            "skinLabA": face_lab_stats["a"],
            "skinLabB": face_lab_stats["b"],
        },
    }

    left_cheek_roi = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.1),
        int(y_min + face_h * 0.34),
        int(x_min + face_w * 0.34),
        int(y_min + face_h * 0.63),
    )
    right_cheek_roi = _crop_np(
        image_rgb,
        int(x_max - face_w * 0.34),
        int(y_min + face_h * 0.34),
        int(x_max - face_w * 0.1),
        int(y_min + face_h * 0.63),
    )
    cheeks_roi = _concat_regions_horizontally(left_cheek_roi, right_cheek_roi)
    nose_roi = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.38),
        int(y_min + face_h * 0.34),
        int(x_max - face_w * 0.38),
        int(y_min + face_h * 0.68),
    )
    chin_roi = _crop_np(
        image_rgb,
        int(x_min + face_w * 0.27),
        int(y_min + face_h * 0.68),
        int(x_max - face_w * 0.27),
        int(y_max - face_h * 0.03),
    )
    cheeks_lab_stats = _region_lab_stats(cheeks_roi)
    nose_lab_stats = _region_lab_stats(nose_roi)
    chin_lab_stats = _region_lab_stats(chin_roi)
    skin_evenness, skin_evenness_score = _skin_evenness(face_roi)
    skin_texture_primary, skin_texture_score = _skin_texture_primary(face_roi)
    skin_shine_level, skin_shine_score = _skin_shine_level(face_roi)
    redness_areas = _redness_areas(
        face_lab_stats,
        cheeks_lab_stats,
        nose_lab_stats,
        chin_lab_stats,
    )
    fine_lines = _fine_lines(eye_roi, sharpness_score)
    wrinkles_depth = _wrinkle_depth(skin_texture_primary, fine_lines)
    freckles, freckles_ratio = _freckles_level(cheeks_roi if cheeks_roi is not None else face_roi)
    moles, moles_ratio = _moles_level(cheeks_roi if cheeks_roi is not None else face_roi)
    recommended_metal_finish, avoid_metal_finish = _recommended_metal_finish(
        color_stats["skinUndertone"],
        skin_shine_level,
        freckles,
        skin_texture_primary,
    )
    skin_analysis = {
        "analysisConfidence": "heuristic",
        "skinToneDepth": _skin_tone_depth(skin_lightness, color_stats["skinUndertone"]),
        "skinUndertone": color_stats["skinUndertone"],
        "skinEvenness": skin_evenness,
        "skinTexturePrimary": skin_texture_primary,
        "skinShineLevel": skin_shine_level,
        "rednessAreas": redness_areas,
        "fineLines": fine_lines,
        "wrinklesDepth": wrinkles_depth,
        "freckles": freckles,
        "moles": moles,
        "recommendedMetalFinish": recommended_metal_finish,
        "avoidMetalFinish": avoid_metal_finish,
        "stoneCutPreference": _stone_cut_preference(
            skin_texture_primary,
            fine_lines,
            "large" if feature_density_ratio >= 0.82 else "medium",
            contrast_style,
        ),
        "metrics": {
            "skinEvennessScore": skin_evenness_score,
            "skinTextureScore": skin_texture_score,
            "skinShineScore": skin_shine_score,
            "frecklesRatio": freckles_ratio,
            "molesRatio": moles_ratio,
        },
    }
    lower_space_ratio = (height - y_max) / max(face_h, 1)
    neck_visibility = "visible" if lower_space_ratio >= 0.22 else "partial" if lower_space_ratio >= 0.08 else "hidden"
    neck_length_px = round(max(0.0, (height - y_max) * 0.72), 1)
    neck_width_px = round(max(1.0, face_w * 0.44), 1)
    neck_length_to_width = round(neck_length_px / max(neck_width_px, 1.0), 3)
    neck_angle = round(abs(eye_slope) * 45.0, 1)
    neck_profile = _neck_profile_label(neck_length_to_width, head_tilt_strong)
    neck_base_type = "broad" if face_w / max(width, 1) >= 0.42 else "narrow"
    collarbone_visibility = _collarbone_visibility(lower_space_ratio, neck_visibility)
    neck_muscle_tone = "high" if neck_length_to_width >= 1.45 else "medium" if neck_length_to_width >= 1.05 else "low"
    skin_laxity = "low" if overall_scale != "delicate" else "medium"
    necklace_types, rigid_choker_risk, pendulum_range, vertical_accent = _necklace_recommendations_from_ratio(
        neck_length_to_width,
        neck_visibility,
        collarbone_visibility,
    )
    decollete_visibility = _decollete_visibility(
        neck_visibility,
        lower_space_ratio,
        collarbone_visibility,
    )
    decollete_collarbone_shape = _collarbone_shape(
        collarbone_visibility,
        neck_base_type,
        overall_horizontal,
    )
    decollete_chest_width = _chest_width_label(face_w / max(width, 1))
    pendant_drop_mm, layering_possible = _decollete_recommendations(
        decollete_visibility,
        decollete_chest_width,
        decollete_collarbone_shape,
        neck_length_to_width,
    )
    neck_analysis_accurate = {
        "analysisConfidence": "heuristic",
        "neckLengthPx": neck_length_px,
        "neckWidthPx": neck_width_px,
        "neckLengthToWidth": neck_length_to_width,
        "neckAngle": neck_angle,
        "neckProfile": neck_profile,
        "neckBaseType": neck_base_type,
        "collarboneVisibility": collarbone_visibility,
        "adamsAppleVisible": False,
        "neckMuscleTone": neck_muscle_tone,
        "skinLaxity": skin_laxity,
        "pendulumLengthRecommendationMm": pendulum_range,
        "rigidChokerRisk": rigid_choker_risk,
        "recommendedNecklaceTypes": necklace_types,
    }
    decollete_analysis = {
        "analysisConfidence": "heuristic",
        "visibility": decollete_visibility,
        "collarboneShape": decollete_collarbone_shape,
        "chestWidth": decollete_chest_width,
        "recommendedPendantDropMm": pendant_drop_mm,
        "recommendedLayeringPossible": layering_possible,
    }
    recommended_textures = ["smooth", "mirror", "delicate_hammered"]

    primary_category, primary_zone_text = _primary_zone(
        overall_vertical,
        neck_visibility,
    )
    if ears_covered == "both":
        earring_length = ["short"]
        primary_category = "necklace"
        primary_zone_text = "зоне шеи"
    elif ears_covered in {"left", "right"}:
        earring_length = ["short", "medium"]

    if hair_volume == "high" and recommended_scale == "mini":
        recommended_scale = "medium"

    avoid_rules = _avoid_rules(
        color_stats["recommendedMetal"],
        overall_scale,
        line_type,
        hair_analysis,
        color_contrast_analysis,
        skin_analysis,
        facial_harmony_analysis,
        neck_analysis_accurate,
    )
    left_visibility_score = _clamp(1.0 - left_cover_ratio, 0.0, 1.0)
    right_visibility_score = _clamp(1.0 - right_cover_ratio, 0.0, 1.0)
    left_visibility = _visibility_label(left_visibility_score)
    right_visibility = _visibility_label(right_visibility_score)
    left_angle = _ear_angle_label(left_visibility, overall_horizontal)
    right_angle = _ear_angle_label(right_visibility, overall_horizontal)
    left_lobe_area_ratio = round(face_area_ratio * left_visibility_score * 0.12, 4)
    right_lobe_area_ratio = round(face_area_ratio * right_visibility_score * 0.12, 4)
    left_lobe_size = _ear_lobe_size(left_lobe_area_ratio)
    right_lobe_size = _ear_lobe_size(right_lobe_area_ratio)
    left_lobe_attachment = _ear_lobe_attachment(left_visibility_score, "defined" if jaw_to_cheek >= 0.94 else "soft")
    right_lobe_attachment = _ear_lobe_attachment(right_visibility_score, "defined" if jaw_to_cheek >= 0.94 else "soft")
    left_lobe_thickness = _ear_lobe_thickness(left_lobe_area_ratio)
    right_lobe_thickness = _ear_lobe_thickness(right_lobe_area_ratio)
    left_lobe_length_mm = round(12 + left_visibility_score * 7, 1)
    right_lobe_length_mm = round(12 + right_visibility_score * 7, 1)
    left_lobe_width_mm = round(7 + left_visibility_score * 4, 1)
    right_lobe_width_mm = round(7 + right_visibility_score * 4, 1)
    avg_visibility = (left_visibility_score + right_visibility_score) / 2.0
    recommended_closures = _recommended_ear_closures(
        left_visibility,
        right_visibility,
        left_lobe_attachment if left_visibility_score >= right_visibility_score else right_lobe_attachment,
        overall_scale,
    )
    max_earring_weight_grams, max_earring_length_mm, heavy_earring_risk = _ear_weight_and_length(
        overall_scale,
        avg_visibility,
        ears_covered,
    )
    ear_shape = _ear_shape_label(face_shape, "defined" if jaw_to_cheek >= 0.94 else "soft")
    helix_visibility = (
        "full"
        if avg_visibility >= 0.7
        else "partial"
        if avg_visibility >= 0.35
        else "hidden"
    )
    antitragus_size = "large" if avg_visibility >= 0.72 else "medium" if avg_visibility >= 0.42 else "small"
    ear_analysis_detailed = {
        "analysisConfidence": "heuristic",
        "leftEar": {
            "visible": left_visibility,
            "visibilityScore": round(left_visibility_score, 3),
            "angle": left_angle,
        },
        "rightEar": {
            "visible": right_visibility,
            "visibilityScore": round(right_visibility_score, 3),
            "angle": right_angle,
        },
        "leftLobe": {
            "size": left_lobe_size,
            "attachmentType": left_lobe_attachment,
            "thickness": left_lobe_thickness,
            "lengthMm": left_lobe_length_mm,
            "widthMm": left_lobe_width_mm,
            "piercingHoles": 1 if left_visibility != "false" else 0,
        },
        "rightLobe": {
            "size": right_lobe_size,
            "attachmentType": right_lobe_attachment,
            "thickness": right_lobe_thickness,
            "lengthMm": right_lobe_length_mm,
            "widthMm": right_lobe_width_mm,
            "piercingHoles": 1 if right_visibility != "false" else 0,
        },
        "earShape": ear_shape,
        "helixVisibility": helix_visibility,
        "antitragusSize": antitragus_size,
        "recommendedClosures": recommended_closures,
        "maxEarringWeightGrams": max_earring_weight_grams,
        "maxEarringLengthMm": max_earring_length_mm,
        "heavyEarringRisk": heavy_earring_risk,
    }
    summary, bullets = _user_summary_v2(
        overall_scale,
        recommended_shapes,
        color_stats["recommendedMetal"],
        primary_zone_text,
        neck_visibility,
    )

    photo_quality = {
        "faceDetected": True,
        "singlePerson": single_person,
        "faceVisibleLarge": face_visible_large,
        "sharpness": sharpness,
        "lightQuality": light_quality,
        "filterDetected": False,
        "headTiltStrong": head_tilt_strong,
        "earVisible": ear_visibility,
        "neckVisible": neck_visibility,
    }
    can_continue = (
        single_person
        and face_visible_large
        and light_quality != "poor"
        and sharpness != "poor"
        and not head_tilt_strong
    )

    return {
        "success": True,
        "can_continue": can_continue,
        "quality_status": "ok" if can_continue else "retry_required",
        "retry_hint": None if can_continue else _quality_retry_hint(photo_quality),
        "analysis": {
            "version": "1.0",
            "photoQuality": photo_quality,
            "faceGeometry": {
                "faceShape": face_shape,
                "faceLength": face_length,
                "faceWidth": face_width,
                "jawlineType": "defined" if jaw_to_cheek >= 0.94 else "soft",
                "cheekboneProminence": "high" if cheek_w / max(face_w, 1) >= 0.76 else "medium",
                "chinType": "soft",
                "foreheadProportion": "balanced",
                "overallVertical": overall_vertical,
                "overallHorizontal": overall_horizontal,
            },
            "appearanceScale": {
                "overallAppearanceScale": overall_scale,
                "featureScale": "large" if feature_density_ratio >= 0.82 else "small" if feature_density_ratio <= 0.56 else "medium",
                "eyeScale": "large" if eye_w / max(face_w, 1) >= 0.38 else "small" if eye_w / max(face_w, 1) <= 0.25 else "medium",
                "lipScale": "large" if mouth_w / max(face_w, 1) >= 0.44 else "small" if mouth_w / max(face_w, 1) <= 0.3 else "medium",
                "noseScale": "large" if nose_w / max(face_w, 1) >= 0.16 else "small" if nose_w / max(face_w, 1) <= 0.1 else "medium",
                "featureDensity": feature_density,
                "allowedJewelryScale": recommended_scale,
                "riskOfOverload": "high" if overall_scale == "delicate" else "medium",
            },
            "lineAnalysis": {
                "lineType": line_type,
                "dominantLineDirection": "elongated" if overall_vertical == "elongated" else "rounded",
                "softnessLevel": "medium",
                "graphicLevel": "high" if line_type == "graphic" else "medium",
                "visualStrictness": "strict" if line_type == "graphic" else "balanced",
                "visualNaturalness": "medium",
            },
            "colorAnalysis": {
                "eyeColor": eye_color,
                "hairColor": hair_color,
                "hairDepth": hair_depth,
                "skinUndertone": color_stats["skinUndertone"],
                "appearanceLightness": color_stats["appearanceLightness"],
                "contrastLevel": formula_contrast_level,
                "appearanceBrightness": color_stats["appearanceBrightness"],
                "recommendedMetal": color_stats["recommendedMetal"],
                "recommendedStonePalette": recommended_stone_palette,
            },
            "hairAnalysis": hair_analysis,
            "colorContrastAnalysis": color_contrast_analysis,
            "skinAnalysis": skin_analysis,
            "facialHarmonyAnalysis": facial_harmony_analysis,
            "vibeAnalysis": vibe_analysis,
            "textureAnalysis": {
                "skinTextureVisual": (
                    "smooth"
                    if skin_texture_primary in {"smooth", "fine_pores"}
                    else "delicate_lively"
                ),
                "frecklesVisible": freckles,
                "fineLinesVisible": fine_lines,
                "overallTexture": "soft" if skin_texture_primary != "textured" else "contrasty",
                "textureContrast": "high" if skin_texture_primary == "textured" else "medium",
                "recommendedTextures": recommended_textures + recommended_metal_finish[:1],
                "textureOverloadRisk": (
                    "high"
                    if overall_scale == "delicate" or skin_texture_primary == "textured"
                    else "medium"
                    if skin_shine_level == "oily"
                    else "low"
                ),
            },
            "earAndLobeAnalysis": {
                "earVisibility": "both" if left_visibility != "false" and right_visibility != "false" else "partial" if left_visibility != "false" or right_visibility != "false" else "hidden",
                "earlobeSize": left_lobe_size if left_visibility_score >= right_visibility_score else right_lobe_size,
                "earlobeType": left_lobe_attachment if left_visibility_score >= right_visibility_score else right_lobe_attachment,
                "earlobeCondition": "unknown",
                "piercingCountVisible": (
                    ear_analysis_detailed["leftLobe"]["piercingHoles"]
                    + ear_analysis_detailed["rightLobe"]["piercingHoles"]
                ),
                "currentEarringFit": "unclear",
                "recommendedEarringWeight": "light" if max_earring_weight_grams <= 8 else "light_medium",
                "recommendedEarringClosure": recommended_closures,
                "heavyEarringRisk": heavy_earring_risk,
            },
            "earAnalysisDetailed": ear_analysis_detailed,
            "neckAnalysis": {
                "neckLength": "long" if lower_space_ratio >= 0.28 else "medium" if lower_space_ratio >= 0.12 else "short",
                "neckVisibility": neck_visibility,
                "neckDelicacy": "medium",
                "recommendedNecklaceLength": necklace_types,
                "shorteningRisk": "high" if rigid_choker_risk == "high" else "medium" if rigid_choker_risk == "medium" else "low",
                "verticalAccentNeeded": vertical_accent,
            },
            "neckAnalysisAccurate": neck_analysis_accurate,
            "decolleteAnalysis": decollete_analysis,
            "accentZones": {
                "primaryAccentZone": primary_category,
                "secondaryAccentZone": "earrings" if primary_category == "necklace" else "necklace" if neck_visibility != "hidden" else "rings",
                "accentNearFace": "yes",
                "accentOnNeck": "moderate" if neck_visibility != "hidden" else "no",
                "accentOnHands": "optional",
            },
            "recommendations": {
                "primaryCategory": primary_category,
                "recommendedCategories": [primary_category, "earrings" if primary_category != "earrings" else "necklace", "rings"],
                "recommendedScale": recommended_scale,
                "recommendedEarringLength": earring_length,
                "recommendedEarringWeight": "light" if max_earring_weight_grams <= 8 else "light_medium",
                "recommendedNecklaceLength": necklace_types,
                "recommendedPendantDropMm": pendant_drop_mm,
                "recommendedLayeringPossible": layering_possible,
                "recommendedShapes": recommended_shapes,
                "recommendedTextures": recommended_textures + recommended_metal_finish[:1],
                "recommendedMetals": color_stats["recommendedMetals"],
                "avoidAsPrimary": ["too_heavy", "too_tiny"] if overall_scale == "delicate" else ["too_tiny"],
                "recommendedStoneIntensity": stone_intensity,
                "recommendedContrastStyle": contrast_style,
                "symmetryImportance": symmetry_importance,
                "recommendedSymmetry": recommended_symmetry,
                "recommendedJewelryMood": vibe_analysis["recommendedJewelryMood"],
                "avoidRules": avoid_rules,
                "stylistSummaryInternal": summary,
                "metal_colors": color_stats["recommendedMetals"],
                "stone_colors": recommended_stone_palette,
                "styles": (
                    ["графичный", "структурный"]
                    if line_type == "graphic"
                    else ["элегантный", "спокойный"]
                ),
            },
            "userFacing": {
                "summary": summary,
                "bullets": bullets,
            },
            "debug": {
                "pipelineVersion": "mediapipe-color-v1",
                "provider": "ml-service",
                "filename": filename,
                "imageSize": {"width": width, "height": height},
                "metrics": {
                    "faceAreaRatio": round(face_area_ratio, 4),
                    "faceRatio": round(face_ratio, 4),
                    "jawToCheek": round(jaw_to_cheek, 4),
                    "eyeSlope": round(eye_slope, 4),
                    "sharpnessScore": round(sharpness_score, 4),
                    "faceBrightness": round(face_brightness, 4),
                    "mouthToNoseRatio": round(mouth_to_nose_ratio, 4),
                    "centerAlignmentDeviation": center_alignment_deviation,
                    **color_stats["metrics"],
                },
                "limitations": warnings + [
                    "Hair segmentation is heuristic and should be replaced with a dedicated model",
                    "Ear/lobe analysis is face-adjacent heuristic and should be replaced with dedicated ear landmarks",
                    "Neck analysis is heuristic and should be upgraded with dedicated pose landmarks",
                    "Skin analysis is heuristic and should be validated on controlled-light portraits",
                ],
            },
        },
    }


def analyze_photo_baseline(
    photo_data: bytes,
    filename: str | None = None,
) -> dict[str, Any]:
    image = Image.open(BytesIO(photo_data)).convert("RGB")
    if np is None:
        return _build_baseline_analysis(photo_data, filename=filename)

    image_rgb = np.array(image)

    if mp is None:
        return _build_baseline_analysis(photo_data, filename=filename)

    try:
        return _build_mediapipe_analysis(image_rgb, filename=filename)
    except Exception:
        logger.exception("MediaPipe analysis failed, falling back to baseline pipeline")
        return _build_baseline_analysis(photo_data, filename=filename)
