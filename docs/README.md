# GLAME Platform Documentation

This index is the source of truth for platform documentation. The root README gives a quick start and high-level map; detailed docs live here.

## Architecture

- `architecture/PLATFORM_STRUCTURE.md` — platform structure. Needs refresh after cleanup.
- `architecture/PLATFORM_NAVIGATION.md` — navigation map. Needs refresh after cleanup.
- `architecture/BRAND_KNOWLEDGE.md` — brand knowledge / RAG context.
- `agents-architecture.md` — agent architecture.
- `authentication.md` — auth model.

## Customer app

- `app/mobile/mobile_app_plan.md` or current `mobile_app_plan.md` — mobile app plan.
- `app/mobile/mobile_app_ui_spec.md` or current `mobile_app_ui_spec.md` — UI spec.
- `design/GLAME_updated_document_system_v2_FULL/` — current design system for app pages.
- `design/` — app design assets and per-block logic.
- `flutter_web_deploy.md` — Flutter web deployment.

## Web admin / platform

- `admin/GLAME_AI_Platform_Enterprise_Blueprint.md`
- `admin/GLAME_AI_Platform_TZ_Team_Agents_UPDATED.md`
- `admin/GLAME_AI_Platform_Boards_Implementation_Plan.md`
- `admin/glame_ai_platform_boards_ui_logic_specification.md`
- `admin/GLAME_AI_Agent_System_Prompts_v1.md`
- `admin/GLAME_AI_Agent_System_Prompts_v1_2.md`

## Product domains

### Catalog / products

- `product/catalog/PRODUCT_TABLES_STRUCTURE.md`
- `product/catalog/PRODUCT_LINKING_GUIDE.md`
- `product/catalog/CHARACTERISTICS_LOADING_GUIDE.md`
- `product/catalog/MAPPING_FIXES_SUMMARY.md`

### Analytics

- `product/analytics/ANALYTICS_API_EXAMPLES.md`
- `product/analytics/ANALYTICS_INTEGRATION_README.md`
- `product/analytics/ANALYTICS_QUICK_START.md`
- `product/analytics/YANDEX_METRIKA_TOKEN_GUIDE.md`

### Content agent

- `product/content-agent/CONTENT_AGENT_GUIDE.md`
- `product/content-agent/CONTENT_AGENT_INTEGRATION.md`
- `product/content-agent/CONTENT_AGENT_USAGE.md`

### Customers / CRM

- `product/customers/CUSTOMER_SYSTEM_GUIDE.md`

## Integrations

### 1C

- `integrations/1c/1C_INTEGRATION.md`
- `integrations/1c/1C_CUSTOMERS_INTEGRATION.md`
- `integrations/1c/1C_AVAILABLE_COLLECTIONS.md`
- `integrations/1c/1C_PRODUCT_CHARACTERISTICS.md`
- `integrations/1c/1C_PRODUCT_MAPPING.md`
- `integrations/1c/FTP_SYNC_USAGE.md`
- `integrations/1c/ODATA_PRODUCTS_REMOVAL_SUMMARY.md`

### Other integrations

- `sms_integration_plan.md`
- shipping/payment docs to be organized under `integrations/shipping/` and `integrations/payments/` if/when expanded.

## Operations

- `operations/DEPLOY.md`
- `operations/INIT_DATABASE.md`
- `operations/QUICK_START_DB.md`
- `operations/environment/ENV.legacy.example`
- `operations/environment/ENV_VARIABLES_TEMPLATE.txt`
- `ml_service.md` — ML service.

## Archive

Historical or superseded documents live under `archive/`. Keep them when they explain past decisions, but do not treat them as current implementation guidance unless refreshed.

- `archive/fixes/` — old one-off fix notes and quick-fix playbooks kept for context.

## Documentation rules

1. New root `.md` files are not allowed unless they are `README.md` or intentionally top-level.
2. New integration docs go under `docs/integrations/<domain>/`.
3. New app design docs go under `docs/design/` or `docs/app/mobile/`.
4. Reports go under `reports/`, not `docs/`, unless they become durable documentation.
5. If a document is obsolete but useful historically, move it to `docs/archive/` instead of deleting it.
