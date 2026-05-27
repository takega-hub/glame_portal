# GLAME AI Platform

Operational AI + commerce platform for GLAME: customer app, admin platform, AI marketer/director agents, catalog and inventory workflows, CRM, analytics, 1C integrations, payments/shipping, and live stylist workflows.

## Main surfaces

### Customer app

Flutter app in `mobile/glame_app`.

Current customer-facing areas include:

- home and onboarding;
- catalog and product page;
- cart and checkout;
- wishlist and looks;
- AI photo selection;
- live stylist chat;
- brands and spaces.

Useful routes in the Flutter web build:

```text
/#/home
/#/home?tab=1
/#/catalog
/#/product/:id
/#/selection/ai-photo
/#/stylist-chat
```

### Web admin / platform

Next.js platform in `frontend`.

Current operational areas include:

- admin app;
- customers and customer segments;
- live stylist;
- cron;
- roles/access;
- shipping;
- AI marketer;
- task boards;
- content agent;
- analytics and product analytics;
- inventory control;
- knowledge base;
- products and looks.

Representative routes:

```text
/admin/app
/admin/customers
/admin/live-stylist
/admin/cron
/admin/roles
/admin/shipping
/ai-marketer
/ai-marketer/tasks
/analytics
/inventory-control
/knowledge-base
/products
/looks
```

### Backend

FastAPI backend in `backend`.

Current API domains include:

- auth;
- products and catalog sections;
- cart, checkout, orders and payments;
- analytics;
- inventory and pricing;
- 1C sync and orders exchange;
- customers, CRM and segmentation;
- communication;
- content agent;
- stylist and live stylist;
- AI marketer and director agents;
- app public API;
- admin APIs;
- shipping.

## Repository structure

```text
backend/           FastAPI backend
frontend/          Next.js admin/platform frontend
mobile/glame_app/  Flutter customer app
docs/              documentation and design docs
scripts/           dev/deploy/data/audit helpers
infra/             Docker/systemd/nginx infrastructure
data/migrations/   Alembic migrations
ml-service/        ML inference service
reports/           curated audit/QA/sync reports
```

## Quick start

### Infrastructure

```bash
docker-compose -f infra/docker-compose.yml up -d
```

### Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Flutter customer app

```bash
cd mobile/glame_app
flutter pub get
flutter run -d chrome
```

## Documentation

Start with:

- `docs/README.md` — documentation index;
- `docs/design/GLAME_updated_document_system_v2_FULL/00_INDEX_GLAME_DOCUMENT_SYSTEM.md` — customer app design system index;
- `docs/mobile_app_ui_spec.md` — app UI spec;
- `docs/admin/` — admin/platform and agent docs;
- `docs/integrations/1c/` — 1C integration docs;
- `docs/operations/` — deploy/database/environment operations docs.

## Repository hygiene

Do not commit:

- `.env` or local secrets;
- `.venv/`, `backend/.venv/`, `venv/`;
- `node_modules/`, `.next/`, build outputs;
- `android-sdk/`;
- runtime uploads/static generated media;
- temporary screenshots/test reports.

Use `reports/` only for curated durable reports. Temporary/generated outputs should stay ignored or outside the repository.

## Development process

- Customer app page design: agree with Elena first, then implement with Anatoly.
- Kanban/GLAME platform tasks: do not move to Done without a verified result.
- Catalog rule: products without photos are hidden; out-of-stock products may be shown with clear unavailable status and `Сообщить о поступлении` flow.
- Keep cleanup commits separate from behavior changes.

## API documentation

When backend is running, API docs are exposed through the configured docs/OpenAPI endpoints. In production/staging, prefer the configured proxy/API base URL rather than hardcoded localhost.

## License

Proprietary — GLAME AI Platform.
