from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.pipeline import analyze_photo_baseline


app = FastAPI(title="GLAME ML Service", version="1.0.0")
MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze-face")
async def analyze_face(photo: UploadFile = File(...)) -> dict:
    try:
        photo_data = await photo.read()
        if not photo_data:
            raise HTTPException(status_code=400, detail="Empty image payload")
        if len(photo_data) > MAX_PHOTO_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Image payload is too large")

        try:
            Image.open(BytesIO(photo_data)).verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=400, detail="Unsupported or corrupted image") from exc

        return analyze_photo_baseline(
            photo_data=photo_data,
            filename=photo.filename,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"ML analyze-face failed: {exc}",
        ) from exc
