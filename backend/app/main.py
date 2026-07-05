from fastapi import FastAPI, Request, Query, Depends
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import traceback
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

root_env_path = Path(__file__).resolve().parents[2] / ".env"
backend_env_path = Path(__file__).resolve().parents[1] / ".env"

if root_env_path.exists():
    load_dotenv(str(root_env_path), override=False)
if backend_env_path.exists():
    load_dotenv(str(backend_env_path), override=False)

from app.api import products, looks, auth, stylist, content, analytics, stores, persona, marketing, inventory, pricing
from app.api.auth import get_current_user
from app.api import onec_sync, knowledge, catalog_sections
from app.api import settings, look_tryon, customer_cabinet, ai_marketer, communication
from app.api import app_public
from app.api import agent_system_prompts, agent_interactions, customer_segmentation, director, consultant_training
from app.api import cart_checkout
from app.api import yookassa_webhook
from app.api import orders_payments
from app.api import onec_orders_exchange
from app.api import shipping_cdek
from app.api import gift_certificates
from app.api import referrals
from app.api.admin import customers as admin_customers, onec_customers, app_admin, live_stylist
from app.api.admin import shipping_admin, access as admin_access, cron as admin_cron, system as admin_system
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
from app.services.inventory_recalc_scheduler import (
    start_inventory_recalc_scheduler,
    stop_inventory_recalc_scheduler,
)
from app.services.receipt_bundle_recalc_scheduler import (
    start_receipt_bundle_recalc_scheduler,
    stop_receipt_bundle_recalc_scheduler,
)
from app.services.store_visits_sync_scheduler import (
    start_nightly_store_visits_sync_scheduler,
    stop_nightly_store_visits_sync_scheduler,
)  # Остатки товаров по складам для аналитики
from app.services.onec_user_sync_scheduler import (
    start_onec_user_sync_scheduler,
    stop_onec_user_sync_scheduler,
)
from app.services.onec_sales_sync_scheduler import (
    start_onec_sales_sync_scheduler,
    stop_onec_sales_sync_scheduler,
)
from app.services.glame_token_scheduler import (
    start_glm_hold_release_scheduler,
    start_glm_onec_bridge_retry_scheduler,
    start_glm_telegram_alert_scheduler,
    start_glm_ton_auto_transfer_scheduler,
    start_glm_ton_settlement_scheduler,
    stop_glm_hold_release_scheduler,
    stop_glm_onec_bridge_retry_scheduler,
    stop_glm_telegram_alert_scheduler,
    stop_glm_ton_auto_transfer_scheduler,
    stop_glm_ton_settlement_scheduler,
)
from app.services.cron_registry import start_admin_cron_scheduler, stop_admin_cron_scheduler

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
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
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
            # Обработка фото украшений через Hermes GPT Image 2 может занимать несколько минут.
            try:
                response = await asyncio.wait_for(call_next(request), timeout=600.0)  # 10 минут
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
    await start_inventory_recalc_scheduler(app)
    await start_receipt_bundle_recalc_scheduler(app)
    await start_onec_user_sync_scheduler(app)
    await start_onec_sales_sync_scheduler(app)
    await start_glm_hold_release_scheduler(app)
    await start_glm_ton_settlement_scheduler(app)
    await start_glm_ton_auto_transfer_scheduler(app)
    await start_glm_onec_bridge_retry_scheduler(app)
    await start_glm_telegram_alert_scheduler(app)
    await start_admin_cron_scheduler(app)
    from app.api.communication import start_generated_messages_sync
    # await start_generated_messages_sync(app)


@app.on_event("shutdown")
async def shutdown_event():
    # Отключена автоматическая синхронизация покупателей по расписанию
    # await stop_customer_sync_scheduler(app)
    # Отключено ночное обновление всех покупателей
    # await stop_nightly_customer_sync_scheduler(app)
    await stop_nightly_stock_sync_scheduler(app)
    await stop_nightly_store_visits_sync_scheduler(app)
    await stop_inventory_recalc_scheduler(app)
    await stop_receipt_bundle_recalc_scheduler(app)
    await stop_onec_user_sync_scheduler(app)
    await stop_onec_sales_sync_scheduler(app)
    await stop_glm_telegram_alert_scheduler(app)
    await stop_glm_onec_bridge_retry_scheduler(app)
    await stop_glm_ton_auto_transfer_scheduler(app)
    await stop_glm_ton_settlement_scheduler(app)
    await stop_glm_hold_release_scheduler(app)
    await stop_admin_cron_scheduler(app)
    from app.api.communication import stop_generated_messages_sync
    # await stop_generated_messages_sync(app)

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
default_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:8899",
    "http://localhost:9090",
    "http://localhost:9091",
]

env_cors = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
env_cors_origins = [x.strip() for x in env_cors.split(",") if x.strip()] if env_cors else []

allow_origins = list(dict.fromkeys([*default_cors_origins, *env_cors_origins]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
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
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(pricing.router, prefix="/api/pricing", tags=["pricing"])
app.include_router(stores.router, prefix="/api/stores", tags=["stores"])
app.include_router(persona.router, prefix="/api/persona", tags=["persona"])
app.include_router(marketing.router, prefix="/api/marketing", tags=["marketing"])
app.include_router(onec_sync.router)
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(customer_cabinet.router, prefix="/api/customer", tags=["customer"])
app.include_router(admin_customers.router, prefix="/api/admin/customers", tags=["admin-customers"])
app.include_router(onec_customers.router, prefix="/api/admin/1c", tags=["admin-1c"])
app.include_router(app_admin.router, prefix="/api/admin/app", tags=["admin-app"])
app.include_router(shipping_admin.router, prefix="/api/admin/shipping", tags=["admin-shipping"])
app.include_router(admin_access.router, prefix="/api/admin/access", tags=["admin-access"])
app.include_router(live_stylist.router, prefix="/api/admin/live-stylist", tags=["admin-live-stylist"])
app.include_router(admin_cron.router, prefix="/api/admin/cron", tags=["admin-cron"])
app.include_router(admin_system.router, prefix="/api/admin/system", tags=["admin-system"])
app.include_router(app_public.router, prefix="/api/app", tags=["app"])
# Compatibility for older mobile/proxy builds that call public app endpoints
# without the /api prefix.
app.include_router(app_public.router, prefix="/app", tags=["app-compat"])
app.include_router(ai_marketer.router, prefix="/api/ai-marketer", tags=["ai-marketer"])
app.include_router(communication.router, prefix="/api/communication", tags=["communication"])
app.include_router(agent_system_prompts.router, prefix="/api/agent-system-prompts", tags=["agent-system-prompts"])
app.include_router(agent_interactions.router, prefix="/api/agent-interactions", tags=["agent-interactions"])
app.include_router(customer_segmentation.router, prefix="/api/customer-segmentation", tags=["customer-segmentation"])
app.include_router(consultant_training.router, prefix="/api", tags=["consultant-training"])
app.include_router(cart_checkout.router, prefix="/api", tags=["ecommerce"])
app.include_router(yookassa_webhook.router, prefix="/api", tags=["payments"])
app.include_router(orders_payments.router, prefix="/api", tags=["orders"])
app.include_router(onec_orders_exchange.router, prefix="/api", tags=["1c-orders"])
app.include_router(shipping_cdek.router, prefix="/api", tags=["shipping"])
app.include_router(gift_certificates.router, prefix="/api", tags=["gift-certificates"])
app.include_router(referrals.router, prefix="/api/referrals", tags=["referrals"])
app.include_router(director.router)

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


@app.get("/docs", include_in_schema=False)
async def get_documentation(current_user = Depends(get_current_user)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="GLAME AI Platform API")


@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(current_user = Depends(get_current_user)):
    return get_redoc_html(openapi_url="/openapi.json", title="GLAME AI Platform API")


@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(current_user = Depends(get_current_user)):
    return get_openapi(title="GLAME AI Platform API", version="1.0.0", routes=app.routes)



@app.get("/docs", include_in_schema=False)
async def get_documentation(current_user = Depends(get_current_user)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="GLAME AI Platform API")


@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(current_user = Depends(get_current_user)):
    return get_redoc_html(openapi_url="/openapi.json", title="GLAME AI Platform API")


@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint(current_user = Depends(get_current_user)):
    return get_openapi(title="GLAME AI Platform API", version="1.0.0", routes=app.routes)



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
