from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import Optional, Any
from app.database.connection import get_db, AsyncSessionLocal
from app.api.auth import get_current_user
from app.services.look_tryon_service import look_tryon_service
from app.agents.photo_analysis_interpreter_agent import PhotoAnalysisInterpreterAgent
from app.agents.stylist_agent import StylistAgent
from app.models.look import Look
from app.models.product import Product
from app.models.user import User
from app.schemas.photo_analysis import PhotoAnalysisApiResponse
from uuid import UUID
import logging
import base64

logger = logging.getLogger(__name__)

router = APIRouter()


def _make_serializable(obj: Any) -> Any:
    """Рекурсивно преобразует объект в сериализуемый формат для JSON"""
    if isinstance(obj, bytes):
        # Конвертируем бинарные данные в base64 строку
        return base64.b64encode(obj).decode('utf-8')
    elif isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # Для других типов пробуем преобразовать в строку
        return str(obj)


async def _persist_photo_analysis(
    db: AsyncSession,
    look_id: UUID,
    serializable_analysis: dict[str, Any],
) -> None:
    result = await db.execute(select(Look).where(Look.id == look_id))
    look = result.scalar_one_or_none()
    if not look:
        return

    metadata = dict(look.generation_metadata or {})
    metadata["photo_analysis"] = serializable_analysis
    metadata["photo_analysis_version"] = (
        serializable_analysis.get("analysis", {})
        .get("debug", {})
        .get("pipelineVersion", "1.0")
    )
    metadata["photo_analysis_source"] = (
        serializable_analysis.get("analysis", {})
        .get("debug", {})
        .get("provider", "look_tryon")
    )
    metadata["user_facing_summary"] = serializable_analysis.get("user_facing", {})
    metadata["human_readable"] = serializable_analysis.get("human_readable", {})
    metadata["saved_analysis_url"] = serializable_analysis.get("saved_analysis_url")
    look.generation_metadata = metadata
    await db.commit()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _category_tokens(category: str) -> list[str]:
    normalized = category.strip().lower()
    mapping = {
        "earrings": ["серьг", "пусет", "кафф", "earring"],
        "necklace": ["колье", "цеп", "подвес", "кулон", "necklace", "pendant"],
        "rings": ["кольц", "ring"],
        "bracelets": ["браслет", "bracelet"],
    }
    return mapping.get(normalized, [normalized])


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _product_payload(product: Product) -> dict[str, Any]:
    return {
        "id": str(product.id),
        "name": product.name,
        "brand": product.brand,
        "price": product.price,
        "category": product.category,
        "images": product.images or [],
        "description": product.description,
        "article": product.article,
        "weight": product.weight,
    }


def _product_signature(product: Product) -> str:
    name = (product.name or "").strip().lower()
    category = (product.category or "").strip().lower()
    return "|".join([name, category])


def _analysis_recommendations(analysis_payload: dict[str, Any]) -> dict[str, Any]:
    recommendations = analysis_payload.get("recommendations")
    if isinstance(recommendations, dict):
        return recommendations
    nested = analysis_payload.get("analysis")
    if isinstance(nested, dict):
        nested_recommendations = nested.get("recommendations")
        if isinstance(nested_recommendations, dict):
            return nested_recommendations
    return {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _season_keywords(season: str) -> list[str]:
    mapping = {
        "spring": ["весна", "spring"],
        "summer": ["лето", "summer"],
        "autumn": ["осень", "autumn"],
        "winter": ["зима", "winter"],
    }
    return mapping.get(season.strip().lower(), [])


def _metal_indicators() -> dict[str, list[str]]:
    return {
        "gold": ["золот", "позолот", "gold", "golden", "bicolor", "bicolour", "биколор"],
        "silver": ["серебр", "родиев", "silver", "rhodium", "white gold", "белое золото"],
        "mixed": ["микс", "mixed", "combo", "комбо", "bicolor", "bicolour", "биколор"],
    }


def _mentioned_metals(text: str) -> set[str]:
    mentioned: set[str] = set()
    for metal, indicators in _metal_indicators().items():
        if any(indicator in text for indicator in indicators):
            mentioned.add(metal)
    return mentioned


def _passes_metal_filter(text: str, allowed_metals: list[str], forbidden_metals: list[str]) -> bool:
    allowed = {metal.strip().lower() for metal in allowed_metals if metal.strip()}
    forbidden = {metal.strip().lower() for metal in forbidden_metals if metal.strip()}
    mentioned = _mentioned_metals(text)

    if forbidden and mentioned.intersection(forbidden):
        return False
    if allowed and mentioned and not mentioned.intersection(allowed):
        return False
    return True


def _undertone_keywords(undertone: str) -> list[str]:
    mapping = {
        "warm": ["тепл", "warm", "золот"],
        "cool": ["холод", "cool"],
        "neutral": ["нейтрал", "neutral", "сбаланс"],
        "olive": ["олив", "olive"],
    }
    return mapping.get(undertone.strip().lower(), [])


def _style_keywords(line_type: str, vibe: str) -> list[str]:
    line_mapping = {
        "graphic": ["граф", "структур", "собран"],
        "organic": ["мягк", "естествен", "плавн"],
        "soft_geometric": ["элегант", "мягк", "структур"],
    }
    vibe_mapping = {
        "elegant": ["элегант", "сдержан"],
        "romantic": ["романт", "нежн"],
        "bold": ["смел", "выразит"],
        "sweet": ["мягк", "деликат"],
        "mysterious": ["загад", "граф"],
    }
    return line_mapping.get(line_type.strip().lower(), []) + vibe_mapping.get(vibe.strip().lower(), [])


def _build_consistency_checks(analysis_payload: dict[str, Any]) -> dict[str, Any]:
    analysis = _as_dict(analysis_payload.get("analysis"))
    recommendations = _analysis_recommendations(analysis_payload)
    human_readable = _as_dict(analysis_payload.get("human_readable"))
    color_analysis = _as_dict(analysis.get("colorAnalysis"))
    color_contrast = _as_dict(analysis.get("colorContrastAnalysis"))
    vibe_analysis = _as_dict(analysis.get("vibeAnalysis"))
    line_analysis = _as_dict(analysis.get("lineAnalysis"))

    structured_contrast = _normalized_text(color_analysis.get("contrastLevel"))
    formula_contrast = _normalized_text(color_contrast.get("valueContrastBand"))
    contrast_matches = bool(structured_contrast) and structured_contrast == formula_contrast

    stone_palette = _string_list(
        recommendations.get("stone_colors") or color_contrast.get("recommendedStonePalette")
    )
    stone_intensity = _normalized_text(
        recommendations.get("recommendedStoneIntensity") or color_contrast.get("recommendedStoneIntensity")
    )
    palette_by_intensity = {
        "pastel": {"pastel", "soft", "peach"},
        "medium": {"soft", "balanced", "warm"},
        "saturated": {"rich", "saturated", "contrast"},
        "deep": {"deep", "contrast", "dark"},
    }
    expected_palette = palette_by_intensity.get(stone_intensity, set())
    palette_matches = not expected_palette or bool(set(stone_palette) & expected_palette)

    human_color_type = _normalized_text(human_readable.get("color_type"))
    season_type = _normalized_text(color_contrast.get("colorSeasonType"))
    undertone = _normalized_text(color_analysis.get("skinUndertone"))
    season_ok = not season_type or _contains_any(human_color_type, _season_keywords(season_type))
    undertone_ok = not undertone or _contains_any(human_color_type, _undertone_keywords(undertone))
    human_color_matches = bool(human_color_type) and season_ok and undertone_ok

    human_style_type = _normalized_text(human_readable.get("style_type"))
    line_type = _normalized_text(line_analysis.get("lineType"))
    primary_impression = _normalized_text(vibe_analysis.get("primaryImpression"))
    style_keywords = _style_keywords(line_type, primary_impression)
    human_style_matches = bool(human_style_type) and (
        not style_keywords or _contains_any(human_style_type, style_keywords)
    )

    notes: list[str] = []
    if not contrast_matches:
        notes.append("contrastLevel не совпадает с valueContrastBand")
    if not palette_matches:
        notes.append("stone_colors не согласованы с recommendedStoneIntensity")
    if human_color_type and not human_color_matches:
        notes.append("human_readable.color_type не отражает season/undertone")
    if human_style_type and not human_style_matches:
        notes.append("human_readable.style_type слабо согласован с lineType/vibe")

    return {
        "analysisConfidence": "rule_based_v1",
        "contrastConsistency": {
            "structuredContrastLevel": structured_contrast,
            "formulaContrastBand": formula_contrast,
            "matches": contrast_matches,
        },
        "stonePaletteConsistency": {
            "recommendedStoneIntensity": stone_intensity,
            "stoneColors": stone_palette,
            "matches": palette_matches,
        },
        "humanReadableColorConsistency": {
            "humanReadableColorType": human_color_type,
            "seasonType": season_type,
            "undertone": undertone,
            "matches": human_color_matches,
        },
        "humanReadableStyleConsistency": {
            "humanReadableStyleType": human_style_type,
            "lineType": line_type,
            "primaryImpression": primary_impression,
            "matches": human_style_matches,
        },
        "allChecksPassed": contrast_matches and palette_matches and human_color_matches and human_style_matches,
        "notes": notes,
    }


def _category_exact_matches(category: str) -> list[str]:
    normalized = category.strip().lower()
    mapping = {
        "earrings": ["серьги", "каффы"],
        "necklace": ["колье"],
        "rings": ["кольца"],
        "bracelets": ["браслеты"],
    }
    return mapping.get(normalized, [])


async def _recommended_products_for_analysis(
    db: AsyncSession,
    analysis_payload: dict[str, Any],
    limit: int = 6,
) -> list[dict[str, Any]]:
    if analysis_payload.get("can_continue") is not True:
        return []

    recommendations = _analysis_recommendations(analysis_payload)
    if not recommendations:
        return []

    categories = _string_list(recommendations.get("recommendedCategories"))
    metals = _string_list(
        recommendations.get("metal_colors") or recommendations.get("recommendedMetals")
    )
    shapes = _string_list(recommendations.get("recommendedShapes"))
    stone_colors = _string_list(recommendations.get("stone_colors"))
    avoid_rules = recommendations.get("avoidRules")
    avoid_shapes = _string_list(
        avoid_rules.get("shapeForbidden") if isinstance(avoid_rules, dict) else []
    )
    avoid_stones = _string_list(
        avoid_rules.get("stoneForbidden") if isinstance(avoid_rules, dict) else []
    )
    forbidden_metals = _string_list(
        avoid_rules.get("metalForbidden") if isinstance(avoid_rules, dict) else []
    )

    category_conditions = []
    category_tokens: list[str] = []
    exact_categories: list[str] = []
    for category in categories:
        exact_categories.extend(_category_exact_matches(category))
        for token in _category_tokens(category):
            category_tokens.append(token)
            like = f"%{token}%"
            category_conditions.extend(
                [
                    Product.category.ilike(like),
                    Product.name.ilike(like),
                    Product.description.ilike(like),
                ]
            )
        for exact_category in _category_exact_matches(category):
            category_conditions.append(Product.category.ilike(exact_category))

    stmt = select(Product).where(Product.is_active == True)
    if category_conditions:
        stmt = stmt.where(or_(*category_conditions))
    stmt = stmt.limit(150)

    result = await db.execute(stmt)
    products = result.scalars().all()

    scored: list[tuple[int, Product]] = []
    metal_tokens = [metal.strip().lower() for metal in metals if metal.strip()]
    for product in products:
        images = product.images if isinstance(product.images, list) else []
        if not any(isinstance(item, str) and item.strip() for item in images):
            continue

        haystack = " ".join(
            [
                (product.name or ""),
                (product.category or ""),
                (product.description or ""),
                (product.article or ""),
                _flatten_text(product.tags),
                _flatten_text(product.specifications),
                _flatten_text(product.sync_metadata),
            ]
        ).lower()

        if not _passes_metal_filter(haystack, metals, forbidden_metals):
            continue

        score = 0
        if any(
            bad in haystack
            for bad in [
                "салфетк",
                "упаковк",
                "сопутств",
                "подарочн",
            ]
        ):
            continue

        for token in category_tokens:
            if token and token in haystack:
                score += 4
        for exact_category in exact_categories:
            if (product.category or "").strip().lower() == exact_category:
                score += 8

        if "gold" in metal_tokens and any(
            token in haystack for token in ["золот", "gold", "позолот"]
        ):
            score += 3
        if "silver" in metal_tokens and any(
            token in haystack for token in ["серебр", "silver"]
        ):
            score += 3
        if "mixed" in metal_tokens and any(
            token in haystack for token in ["микс", "mixed", "bicolor", "combo"]
        ):
            score += 2

        for shape in shapes:
            normalized_shape = shape.strip().lower()
            if normalized_shape in {"oval", "drop", "soft_geometry", "clean_line"}:
                shape_terms = {
                    "oval": ["овал", "oval"],
                    "drop": ["капл", "drop"],
                    "soft_geometry": ["мягк", "плавн", "soft"],
                    "clean_line": ["линейн", "line", "геометр"],
                }
                if any(term in haystack for term in shape_terms.get(normalized_shape, [])):
                    score += 2

        for stone in stone_colors:
            normalized_stone = stone.strip().lower()
            stone_terms = {
                "peach": ["персик", "peach", "коралл", "жемчуг"],
                "pastel": ["жемчуг", "кварц", "опал", "pastel"],
                "soft": ["молоч", "жемчуг", "soft"],
            }
            if any(term in haystack for term in stone_terms.get(normalized_stone, [])):
                score += 2

        if any(token in haystack for token in avoid_shapes):
            score -= 6
        if any(token in haystack for token in avoid_stones):
            score -= 4

        if product.weight is not None:
            if "earrings" in categories and product.weight <= 12:
                score += 2
            elif "earrings" in categories and product.weight > 18:
                score -= 4

        if product.supports_brand_concept:
            score += 2
        if product.is_core_assortment:
            score += 1

        if score > 0:
            scored.append((score, product))

    scored.sort(
        key=lambda item: (
            -item[0],
            not item[1].supports_brand_concept,
            not item[1].is_core_assortment,
            item[1].price or 0,
        )
    )

    unique_ids: set[str] = set()
    unique_signatures: set[str] = set()
    payload: list[dict[str, Any]] = []
    for _, product in scored:
        product_id = str(product.id)
        if product_id in unique_ids:
            continue
        signature = _product_signature(product)
        if signature in unique_signatures:
            continue
        unique_ids.add(product_id)
        unique_signatures.add(signature)
        payload.append(_product_payload(product))
        if len(payload) >= limit:
            break
    return payload

@router.post("/upload-photo", response_model=dict)
async def upload_user_photo(
    photo: UploadFile = File(...),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    Загрузка фото пользователя
    
    Returns:
        dict: URL сохраненного фото и метаданные
    """
    try:
        requested_user_id = UUID(user_id) if user_id else None
        if requested_user_id and requested_user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Нельзя загружать фото для другого пользователя",
            )

        user_uuid = current_user.id
        photo_data = await photo.read()

        photo_url = await look_tryon_service.save_user_photo(
            photo_data=photo_data,
            user_id=user_uuid,
            filename=photo.filename,
        )

        return {
            "success": True,
            "photo_url": photo_url,
            "filename": photo.filename,
            "user_id": str(user_uuid),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при загрузке фото")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при загрузке фото: {str(e)}"
        )


@router.post("/analyze", response_model=PhotoAnalysisApiResponse)
async def analyze_user_photo(
    photo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Анализ фото пользователя (цветотип, стиль, тип внешности)
    
    Returns:
        PhotoAnalysisResponse: Результат анализа фото
    """
    try:
        photo_data = await photo.read()
        saved_photo_url: str | None = None

        try:
            saved_photo_url = await look_tryon_service.save_user_photo(
                photo_data=photo_data,
                user_id=current_user.id,
                filename=photo.filename,
            )
        except Exception:
            logger.exception("Не удалось сохранить фото пользователя при analyze")
        
        analysis = await look_tryon_service.analyze_photo(
            photo_data=photo_data,
            filename=photo.filename
        )
        interpreter = PhotoAnalysisInterpreterAgent(db)
        analysis["human_readable"] = await interpreter.describe(analysis)
        analysis["recommended_products"] = await _recommended_products_for_analysis(
            db=db,
            analysis_payload=analysis,
        )
        nested_analysis = analysis.get("analysis")
        if isinstance(nested_analysis, dict):
            nested_analysis["consistencyChecks"] = _build_consistency_checks(analysis)
        analysis["saved_photo_url"] = saved_photo_url

        if saved_photo_url:
            try:
                analysis["saved_analysis_url"] = await look_tryon_service.save_photo_analysis_artifacts(
                    photo_url=saved_photo_url,
                    payload=_make_serializable(analysis),
                )
            except Exception:
                logger.exception("Не удалось сохранить sidecar analysis рядом с фото")
                analysis["saved_analysis_url"] = None
        else:
            analysis["saved_analysis_url"] = None

        return PhotoAnalysisApiResponse(**analysis)
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при анализе фото")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при анализе фото")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при анализе фото: {str(e)}"
        )


@router.post("/generate", response_model=dict)
async def generate_look_with_tryon(
    photo: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    look_id: Optional[str] = Form(None),
    user_request: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Генерация образа с примеркой на фото пользователя
    
    Args:
        photo: Фото пользователя
        user_id: ID пользователя (опционально)
        look_id: ID образа для примерки (опционально, если не указан - генерируется новый)
        user_request: Текстовый запрос для генерации (опционально)
    
    Returns:
        dict: Сгенерированный образ с результатом примерки
    """
    try:
        requested_user_id = UUID(user_id) if user_id else None
        if requested_user_id and requested_user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Нельзя запускать примерку для другого пользователя",
            )

        user_uuid = current_user.id
        look_uuid = UUID(look_id) if look_id else None

        photo_data = await photo.read()

        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            
            # Если look_id указан, используем существующий образ
            if look_uuid:
                try_on_result = await agent.try_on_look(
                    look_id=look_uuid,
                    user_photo_data=photo_data,
                    user_id=user_uuid,
                    filename=photo.filename
                )
                # Убеждаемся, что все данные сериализуемы в JSON
                serializable_result = _make_serializable(try_on_result)
                
                return {
                    "success": True,
                    "look_id": str(look_uuid),
                    "try_on_result": serializable_result
                }
            else:
                # Генерируем новый образ
                # Сначала анализируем фото
                photo_analysis = await look_tryon_service.analyze_photo(
                    photo_data=photo_data,
                    filename=photo.filename
                )
                
                # Извлекаем параметры из анализа
                style = photo_analysis.get("style")
                recommendations = photo_analysis.get("recommendations", {})
                
                # Генерируем образ (с изображением на типовой модели, так как фото уже есть)
                generated_look = await agent.generate_look_for_user(
                    user_id=user_uuid,
                    session_id=None,
                    style=style,
                    mood=None,
                    persona=None,
                    user_request=user_request,
                    generate_image=True,
                    use_default_model=True  # Используем типовую модель для визуализации
                )
                
                # Примеряем сгенерированный образ
                if generated_look.get("id"):
                    look_id = UUID(generated_look["id"])
                    try_on_result = await agent.try_on_look(
                        look_id=look_id,
                        user_photo_data=photo_data,
                        user_id=user_uuid,
                        filename=photo.filename
                    )
                    
                    # Убеждаемся, что все данные сериализуемы в JSON
                    serializable_try_on = _make_serializable(try_on_result)
                    serializable_analysis = _make_serializable(photo_analysis)
                    serializable_look = _make_serializable(generated_look)

                    await _persist_photo_analysis(
                        db=db,
                        look_id=look_id,
                        serializable_analysis=serializable_analysis,
                    )
                    
                    return {
                        "success": True,
                        "generated_look": serializable_look,
                        "photo_analysis": serializable_analysis,
                        "user_facing_summary": serializable_analysis.get("user_facing"),
                        "try_on_result": serializable_try_on
                    }
                else:
                    # Убеждаемся, что все данные сериализуемы в JSON
                    serializable_analysis = _make_serializable(photo_analysis)
                    serializable_look = _make_serializable(generated_look)

                    generated_look_id = generated_look.get("id")
                    if generated_look_id:
                        await _persist_photo_analysis(
                            db=db,
                            look_id=UUID(str(generated_look_id)),
                            serializable_analysis=serializable_analysis,
                        )

                    return {
                        "success": True,
                        "generated_look": serializable_look,
                        "photo_analysis": serializable_analysis,
                        "user_facing_summary": serializable_analysis.get("user_facing"),
                        "try_on_result": None
                    }
    except HTTPException:
        raise
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при генерации образа с примеркой")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при генерации образа с примеркой")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при генерации образа с примеркой: {str(e)}"
        )
