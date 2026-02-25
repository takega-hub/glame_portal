"""
Минимальная версия приложения для диагностики проблемы с зависанием
"""
from fastapi import FastAPI

app = FastAPI(
    title="GLAME AI Platform API - Test",
    description="Тестовая версия для диагностики",
    version="1.0.0"
)


@app.get("/")
async def root():
    return {"message": "GLAME AI Platform API", "version": "1.0.0", "status": "test"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
