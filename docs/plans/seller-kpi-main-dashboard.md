# GLAME Главный KPI Dashboard Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after stabilizing current seller matching/deploy issues.

**Goal:** Сделать главный управленческий dashboard по всем магазинам и продавцам: сводка KPI, сравнение магазинов, рейтинг продавцов, прогнозы, риски, динамика роста/падения и переходы на страницы магазинов для настройки планов.

**Architecture:** Новый главный dashboard должен быть read-first управленческой витриной, а настройка планов должна жить на store-level страницах. Backend отдаёт агрегированный snapshot по всем магазинам, frontend рисует инфографику/диаграммы и CTA-переходы. Store detail использует текущую логику `ProfileSellersPage`, но открывается уже в контексте выбранного магазина.

**Tech Stack:** FastAPI/SQLAlchemy/PostgreSQL backend, Next.js React frontend, existing Recharts in `UnifiedAnalyticsPanel.tsx`, existing seller KPI service in `backend/app/services/seller_kpi_service.py`.

---

## Product shape

### Main route

Recommended route:

```text
/profile/sellers/dashboard
```

Alternative if we later merge into global analytics:

```text
/analytics/sellers
```

For current GLAME workflow, `Аккаунт → Продавцы → Дашборд` is best because KPI plans/schedule already live in Account → Sellers.

### Navigation model

Top level:

```text
Продавцы
├── Главный дашборд
├── Магазины / планы
├── График смен
└── Список продавцов
```

Main dashboard is default for admin/manager. Seller role still lands on personal seller cabinet.

### Main dashboard blocks

1. **Executive KPI header**
   - Общая выручка fact/plan/%.
   - Прогноз месяца.
   - Отставание/перевыполнение.
   - Кол-во чеков, изделий, средний чек, длина чека.
   - Кол-во смен и продажи в смену.

2. **Store comparison**
   - Cards per store: revenue, plan, %, forecast, checks, items, avg check, shifts.
   - Horizontal bars by completion.
   - Visual status: green >=100, amber 85-99, red <85.
   - CTA: `Открыть магазин` → `/profile/sellers?tab=kpi&store_name=<exact store_name>` or dedicated store page.

3. **Store dynamics chart**
   - Daily revenue lines/bars per store.
   - Daily completion % line.
   - Visitors/conversion overlay where available.
   - Growth/fall badges versus previous day/week/month.

4. **Seller leaderboard**
   - Top sellers by revenue.
   - Top sellers by % personal plan.
   - Risk sellers below 70/85%.
   - Seller card: fact, personal plan, %, checks, items, shifts/hours.

5. **KPI matrix / heatmap**
   - Rows = stores.
   - Columns = KPI metrics: revenue, checks, items, avg check, avg item price, items/check, shifts, avg sales/shift, traffic, conversion.
   - Cell color by % completion.

6. **Forecast and risk panel**
   - Metrics projected below 100%.
   - Stores projected below plan.
   - Sellers projected below personal plan.
   - Rule-based reasons: low conversion, low avg check, insufficient shifts, traffic drop, product-count anomaly.

7. **Analytical insights**
   - “Центрум: высокий трафик, низкая конверсия — проверить смены/скрипты.”
   - “Ялта: средний чек выше, но не хватает чеков — усилить входящий контакт.”
   - “Продавец X: план по часам высокий, факт отстаёт — разбор смен.”

8. **Data quality panel**
   - Unmatched sellers count.
   - Duplicate store rows count.
   - Excluded packaging/accessory item count.
   - Last 1C sync / last snapshot.
   - Warning if backend is stale or facts/plans split.

---

## Backend tasks

### Task 1: Add all-store KPI dashboard service method

**Objective:** Return one compact payload for all stores/sellers without frontend stitching many endpoints.

**Files:**
- Modify: `backend/app/services/seller_kpi_service.py`
- Modify: `backend/app/api/admin/onec_customers.py`

**Endpoint:**

```text
GET /api/admin/1c/sellers/kpi/dashboard?month=YYYY-MM
```

**Response shape:**

```ts
type SellerKpiDashboardResponse = {
  success: true;
  month: string;
  totals: {
    revenue: number;
    revenue_plan: number;
    completion_percent: number | null;
    forecast_revenue: number | null;
    forecast_percent: number | null;
    checks: number;
    items_sold: number;
    shifts_count: number;
    avg_check: number | null;
    avg_item_price: number | null;
    items_per_check: number | null;
    avg_sales_per_shift: number | null;
  };
  stores: Array<{
    store_name: string;
    revenue: number;
    revenue_plan: number;
    completion_percent: number | null;
    forecast_revenue: number | null;
    forecast_percent: number | null;
    checks: number;
    items_sold: number;
    shifts_count: number;
    avg_check: number | null;
    avg_item_price: number | null;
    items_per_check: number | null;
    avg_sales_per_shift: number | null;
    sellers_count: number;
    risk_level: 'ok' | 'warning' | 'critical';
  }>;
  sellers: SellerKpiRow[];
  metric_matrix: Array<{
    store_name: string;
    metrics: Record<string, { fact: number | null; plan: number | null; percent: number | null }>;
  }>;
  insights: Array<{ type: string; severity: string; title: string; text: string }>;
  data_quality: {
    unmatched_sellers: number;
    duplicate_store_rows: number;
    last_snapshot_date?: string | null;
  };
};
```

**Implementation notes:**
- Reuse `kpi_overview(..., store_name=None)` but ensure it does not split fact/plan rows.
- Reuse `_target_metric_plans(month, store_name=<store>)` for store plan metrics.
- Use exact store names: `ТРК Центрум`, `Ялта, Набережная 18`, `Меганом`.
- Do not run DDL in request path.

**Verification:**

```bash
python -m py_compile backend/app/services/seller_kpi_service.py backend/app/api/admin/onec_customers.py
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/dashboard?month=2026-05'
```

### Task 2: Add dashboard route in frontend API client

**Files:**
- Modify: `frontend/src/lib/api.ts`

Add:

```ts
getSellerKpiDashboard(params: { month?: string })
```

with typed interfaces.

**Verification:**

```bash
cd frontend
npx tsc --noEmit --pretty false
```

### Task 3: Create `SellerKpiMainDashboard` component

**Files:**
- Create: `frontend/src/components/profile/SellerKpiMainDashboard.tsx`

**UI blocks:**
- Executive cards.
- Store comparison cards.
- Recharts composed chart for store comparison.
- Seller leaderboard.
- KPI heatmap table.
- Forecast risk panel.
- Data quality panel.

**Chart dependency:** Use existing `recharts` already used in `UnifiedAnalyticsPanel.tsx`; do not add a new chart library.

**Verification:**

```bash
cd frontend
npx tsc --noEmit --pretty false
npx eslint src/components/profile/SellerKpiMainDashboard.tsx --max-warnings=0
```

### Task 4: Add route/page

**Files:**
- Create: `frontend/src/app/profile/sellers/dashboard/page.tsx`
- Modify: `frontend/src/components/profile/ProfileSellersPage.tsx` or Account navigation config if needed.

Default admin/manager landing should point to dashboard; seller role should remain personal dashboard.

### Task 5: Store drill-down navigation

**Objective:** From dashboard store card, open store KPI configuration page with selected store pre-filled.

**Options:**
1. Query params on existing page:
   - `/profile/sellers?tab=kpi&store_name=ТРК%20Центрум`
2. Dedicated store page:
   - `/profile/sellers/stores/[storeName]`

Recommended MVP: query params to avoid broad routing refactor.

**Modify:**
- `ProfileSellersPage.tsx` should read `tab` and `store_name` from `useSearchParams()`.

### Task 6: Add data-quality guardrails

**Objective:** Dashboard must tell manager/admin if data is not trustworthy.

Show warnings when:
- seller rows contain `seller_name == null` or `Не сопоставлено с продавцом`;
- two store rows have same normalized store name;
- plan-only/fact-only seller split is detected;
- packaging/accessory rows are counted as KPI items;
- latest snapshot is stale.

### Task 7: Visual polish

**Style direction:** premium, clean, executive dashboard.

Use:
- large white cards;
- emerald/amber/red status language;
- thin chart lines;
- heatmap cells;
- clear manager recommendations;
- no overloaded raw tables at the top.

---

## Acceptance criteria

- Admin/manager can open one main seller KPI dashboard and see all stores/sellers at once.
- Dashboard has no plan editing fields.
- Store cards link to store-specific plan setup page.
- Plans remain editable only by admin on store page.
- Manager sees dashboard and drill-down read-only plans.
- Seller role does not see all-store dashboard; seller sees only personal cabinet.
- No duplicate store cards for the same exact store name.
- No `Без имени` seller rows when known 1C IDs exist.
- KPI item/check facts exclude packaging/accessories.
- Frontend passes `tsc` and targeted eslint.
- Backend endpoint returns 200 and payload matches expected shape.
- After deploy/rebuild, live endpoint behavior is verified, not just `/health`.

---

## Suggested implementation order

1. Stabilize current seller matching + rebuild deploy issue.
2. Add read-only backend dashboard endpoint.
3. Add frontend typed API method.
4. Build dashboard MVP with cards, store comparison, seller leaderboard, KPI heatmap.
5. Add drill-down links to store settings.
6. Add forecast/risk/data-quality panels.
7. Verify with May 2026 data for `ТРК Центрум` and `Ялта, Набережная 18`.
