"""Small, dependency-free validation helpers for untrusted uploads."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

MAX_KNOWLEDGE_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ONEC_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_TRAINING_DOCUMENT_BYTES = 20 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def validate_image_upload(content: bytes, content_type: str | None, max_bytes: int = MAX_IMAGE_UPLOAD_BYTES) -> str:
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Размер изображения не должен превышать {max_bytes // (1024 * 1024)} МБ.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            format_name = image.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Содержимое файла не является допустимым изображением.")
    detected = IMAGE_FORMATS.get(format_name or "")
    if not detected:
        raise HTTPException(status_code=400, detail="Поддерживаются только JPEG, PNG и WebP.")
    declared = (content_type or "").lower()
    if declared and declared not in {detected, "image/jpg"}:
        raise HTTPException(status_code=400, detail="MIME-тип не соответствует содержимому изображения.")
    return detected


def validate_knowledge_upload(filename: str | None, content: bytes, content_type: str | None) -> str:
    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".json"}:
        raise HTTPException(status_code=400, detail="Поддерживаются только PDF и JSON файлы.")
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(content) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Размер файла не должен превышать 20 МБ.")
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Содержимое файла не соответствует PDF.")
        return "pdf"
    try:
        json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Содержимое файла не соответствует JSON UTF-8.")
    return "json"


def validate_director_upload(filename: str, content: bytes, content_type: str | None) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Содержимое файла не соответствует PDF.")
    if suffix == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="Содержимое файла не соответствует PNG.")
    if suffix in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="Содержимое файла не соответствует JPEG.")
    if suffix == ".webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
        raise HTTPException(status_code=400, detail="Содержимое файла не соответствует WebP.")
    if suffix == ".json":
        try:
            json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Содержимое файла не соответствует JSON UTF-8.")


def validate_onec_upload(filename: str, content: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".xml", ".json"}:
        raise HTTPException(status_code=400, detail="Поддерживаются только XML и JSON файлы.")
    if not content or len(content) > MAX_ONEC_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Размер файла 1С должен быть от 1 байта до 50 МБ.")
    if suffix == ".xml":
        if not content.lstrip().startswith(b"<"):
            raise HTTPException(status_code=400, detail="Содержимое файла не соответствует XML.")
    else:
        try:
            json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Содержимое файла не соответствует JSON UTF-8.")
    return suffix.lstrip(".")


def validate_training_document(filename: str, content: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".md", ".markdown", ".txt", ".text", ".doc", ".docx", ".pdf"}:
        raise ValueError("unsupported_format")
    if len(content) > MAX_TRAINING_DOCUMENT_BYTES:
        raise ValueError("file_too_large")
    if suffix == ".pdf" and content and not content.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf_content")
    if suffix == ".docx" and content and not content.startswith(b"PK\x03\x04"):
        raise ValueError("invalid_docx_content")
    return suffix.lstrip(".")
