from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api import products, looks, auth, stylist, content, analytics, stores, persona, marketing
from app.api import onec_sync, knowledge, catalog_sections
from app.api import settings, look_tryon, customer_cabinet, ai_marketer, communication
from app.api.admin import customers as admin_customers, onec_customers
from app.services.customer_sync_scheduler import (
    start_customer_sync_scheduler,
    stop_customer_sync_scheduler,
    start_nightly_customer_sync_scheduler,
    stop_nightly_customer_sync_scheduler,
)
from app.services.stock_sync_scheduler import (
    start_nightly_stock_sync_scheduler,
    stop_nightly_stock_sync_scheduler,
)
from app.services.store_visits_sync_scheduler import (
    start_nightly_store_visits_sync_scheduler,
    stop_nightly_store_visits_sync_scheduler,
)  # Остатки товаров по складам для аналитики
import traceback
import sys
import os
from pathlib import Path

# Устанавливаем кодировку UTF-8 для всего приложения
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Таблицы создаются через миграции или SQL скрипты
# Base.metadata.create_all(bind=engine)  # Отключено - используем миграции

app = FastAPI(
    title="GLAME AI Platform API",
    description="AI-платформа для бренда GLAME",
    version="1.0.0"
)

# Увеличиваем таймаут для загрузки файлов
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import asyncio

class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Для эндпоинтов загрузки файлов и генерации образов увеличиваем таймаут
        if request.url.path.startswith("/api/knowledge/upload"):
            try:
                response = await asyncio.wait_for(call_next(request), timeout=600.0)  # 10 минут
                return response
            except asyncio.TimeoutError:
                return JSONResponse(
                    status_code=504,
                    content={"detail": "Request timeout. File processing takes too long."}
                )
        elif request.url.path.startswith("/api/looks/generate"):
            # Для генерации образа (включая генерацию изображения) увеличиваем таймаут до 10 минут
            try:
                response = await asyncio.wait_for(call_next(request), timeout=600.0)  # 10 минут
                return response
            except asyncio.TimeoutError:
                return JSONResponse(
                    status_code=504,
                    content={"detail": "Request timeout. Look generation takes too long. The look may still be created in the background. Please check the looks list in a few minutes."}
                )
        elif request.url.path.startswith("/api/content/jewelry-photo/process"):
            # Обработка фото украшений (несколько изображений, вызов модели)
            try:
                response = await asyncio.wait_for(call_next(request), timeout=120.0)  # 2 минуты
                return response
            except asyncio.TimeoutError:
                return JSONResponse(
                    status_code=504,
                    content={"detail": "Request timeout. Jewelry photo processing takes too long."}
                )
        else:
            return await call_next(request)

app.add_middleware(TimeoutMiddleware)


@app.on_event("startup")
async def startup_event():
    # Очистка старых задач синхронизации
    from app.services.sync_task_manager import task_manager
    task_manager.cleanup_old_tasks(max_age_hours=24)
    
    # Отключена автоматическая синхронизация покупателей по расписанию
    # Синхронизация остается только по запросу (API) и при заходе в карточку покупателя
    # await start_customer_sync_scheduler(app)
    # Отключено ночное обновление всех покупателей - теперь обновление происходит при заходе на страницу конкретного покупателя
    # await start_nightly_customer_sync_scheduler(app)
    await start_nightly_stock_sync_scheduler(app)
    await start_nightly_store_visits_sync_scheduler(app)


@app.on_event("shutdown")
async def shutdown_event():
    # Отключена автоматическая синхронизация покупателей по расписанию
    # await stop_customer_sync_scheduler(app)
    # Отключено ночное обновление всех покупателей
    # await stop_nightly_customer_sync_scheduler(app)
    await stop_nightly_stock_sync_scheduler(app)
    await stop_nightly_store_visits_sync_scheduler(app)

# Глобальный обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    if isinstance(exc, UnicodeDecodeError):
        error_msg = f"Encoding error at position {exc.start}-{exc.end}"
    print("=" * 80)
    print(f"GLOBAL EXCEPTION HANDLER: {type(exc).__name__}: {error_msg}")
    print(f"Request path: {request.url.path}")
    print(f"Request method: {request.method}")
    print(traceback.format_exc())
    print("=" * 80)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {error_msg}"}
    )

# Middleware для обработки кодировки запросов
# Отключаем автоматическую обработку, так как она может мешать обработке бинарных данных
# Ошибки кодировки теперь обрабатываются в конкретных endpoints

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(catalog_sections.router, prefix="/api/catalog-sections", tags=["catalog-sections"])
app.include_router(looks.router, prefix="/api/looks", tags=["looks"])
app.include_router(look_tryon.router, prefix="/api/look-tryon", tags=["look-tryon"])
# Полноценный stylist (AsyncSession)
app.include_router(stylist.router, prefix="/api/stylist", tags=["stylist"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(stores.router, prefix="/api/stores", tags=["stores"])
app.include_router(persona.router, prefix="/api/persona", tags=["persona"])
app.include_router(marketing.router, prefix="/api/marketing", tags=["marketing"])
app.include_router(onec_sync.router)
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(customer_cabinet.router, prefix="/api/customer", tags=["customer"])
app.include_router(admin_customers.router, prefix="/api/admin/customers", tags=["admin-customers"])
app.include_router(onec_customers.router, prefix="/api/admin/1c", tags=["admin-1c"])
app.include_router(ai_marketer.router, prefix="/api/ai-marketer", tags=["ai-marketer"])
app.include_router(communication.router, prefix="/api/communication", tags=["communication"])

# Статические файлы для изображений
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
look_images_dir = static_dir / "look_images"
look_images_dir.mkdir(exist_ok=True)
jewelry_processed_dir = static_dir / "jewelry_processed"
jewelry_processed_dir.mkdir(exist_ok=True)
content_post_images_dir = static_dir / "content_post_images"
content_post_images_dir.mkdir(exist_ok=True)

# Директория для загруженных файлов
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
# Backward compatibility: старые ссылки могли сохраняться как /look_images/<file>
app.mount("/look_images", StaticFiles(directory=str(look_images_dir)), name="look_images")
app.mount("/content_post_images", StaticFiles(directory=str(content_post_images_dir)), name="content_post_images")
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.get("/")
async def root():
    return {"message": "GLAME AI Platform API", "version": "1.0.0"}


@app.get("/health")
async def health(debug: bool = Query(False)):
    """
    Lightweight health check.

    If debug=true (non-production only), includes runtime details to verify which
    interpreter/code is running and what routes are registered.
    """
    payload = {"status": "healthy"}

    if os.environ.get("ENVIRONMENT", "development") == "production" or not debug:
        return payload

    import sys

    try:
        import app.api.content as content_api

        content_file = getattr(content_api, "__file__", None)
        content_routes = []
        for r in getattr(content_api, "router", object()).routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                content_routes.append({"path": r.path, "methods": sorted(list(r.methods))})

        payload.update(
            {
                "sys_executable": sys.executable,
                "cwd": os.getcwd(),
                "content_file": content_file,
                "content_routes_products": [rt for rt in content_routes if "/products" in rt["path"]],
                "content_routes_plans": [rt for rt in content_routes if rt["path"].startswith("/plans")],
            }
        )
    except Exception as e:
        payload.update({"debug_error": str(e), "sys_executable": sys.executable, "cwd": os.getcwd()})

    return payload


# NOTE: keep the surface area small; /health?debug=true is enough for troubleshooting.