# Sales tables: `sales_records` and `purchase_history`

Last updated: 2026-08-01.

This document explains why GLAME currently has two sales-related tables, how they
are updated, which services use them, and how to choose the correct source for a
new feature.

## Short answer

`sales_records` is the detailed 1C sales feed. It stores line-level receipt data
and is the primary source for operational sales analytics, inventory, product
analytics, store dashboards, and director reports.

`purchase_history` is the customer purchase history view. It stores normalized
customer-linked purchase rows and is used by CRM, segmentation, communication,
loyalty, referrals, and customer profile logic.

The current architecture intentionally keeps both:

1. `sales_records` receives fresh receipt data from 1C.
2. `purchase_history` is refreshed from `sales_records` after every sales sync.
3. Existing CRM/customer services continue reading `purchase_history`, avoiding a
   risky migration across many modules.

## Why there are two tables

The tables were created for different consumers.

`sales_records` answers questions like:

- How much did a store sell today?
- How many receipt lines and distinct checks do we have?
- Which products, categories, brands, and stores drive revenue?
- What was imported from 1C in a specific sync batch?

`purchase_history` answers questions like:

- What did this exact customer buy?
- Did a customer buy within 14 days after a CRM touch?
- Which brands/categories are in a customer's history?
- Should a loyalty/referral transaction be connected to a purchase?
- Which users belong to a purchase-based CRM segment?

The important practical difference is identity:

- `sales_records.customer_id` stores the 1C customer key as text.
- `purchase_history.user_id` stores the local GLAME `users.id` UUID.

Many older customer-facing services are built around `users.id`, so they use
`purchase_history`.

## Data ownership

Use this rule unless there is a deliberate migration plan:

- Source of detailed sales truth: `sales_records`.
- Source of customer purchase truth for CRM/customer modules: `purchase_history`.
- Bridge between them: `OneCSalesSyncService.refresh_purchase_history_from_sales_records()`.

Do not manually insert new purchase rows into `purchase_history` for current 1C
sales unless the source is not available in `sales_records`. For normal 1C sales,
load/update `sales_records` and let the refresh step update the customer history
view.

## Table comparison

| Topic | `sales_records` | `purchase_history` |
| --- | --- | --- |
| Main purpose | Detailed 1C receipt/sales fact table | Customer-linked purchase history |
| Main key to customer | `customer_id`, 1C customer key | `user_id`, local `users.id` |
| Amount units | Rubles as `double precision` in `revenue` | Kopecks as integer in `total_amount` and `price` |
| Quantity units | Float in `quantity` | Integer in `quantity` |
| Product key | 1C product key in `product_id` | Local product UUID in `product_id`, 1C key in `product_id_1c` |
| Receipt/document key | `document_id`, `external_id` | `document_id_1c` |
| Freshness | Updated by 1C sales sync | Updated from `sales_records` after sales sync |
| Best for | Sales analytics, inventory, product/store performance | CRM attribution, segmentation, profiles, loyalty/referrals |
| Risk when used incorrectly | Customer attribution may fail for anonymous or unmatched 1C customers | Store/product analytics may miss detail or use older normalized fields |

## `sales_records`

Model: `backend/app/models/sales_record.py`.

Database table: `sales_records`.

### Columns

| Column | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | `uuid` | yes | Local row id. |
| `sale_date` | `timestamp with time zone` | yes | Sale timestamp from 1C. |
| `external_id` | `varchar` | no | Unique 1C row/document-line id used for upsert. |
| `document_id` | `varchar` | no | 1C receipt/document id; use distinct values for check count. |
| `store_id` | `varchar` | no | 1C store/warehouse key. |
| `customer_id` | `varchar` | no | 1C customer key. Can be the all-zero UUID for anonymous sales. |
| `product_id` | `varchar` | no | 1C product/nomenclature key. |
| `organization_id` | `varchar` | no | 1C organization key. |
| `revenue` | `double precision` | yes | Sale amount in rubles. |
| `quantity` | `double precision` | yes | Quantity from the receipt line. |
| `revenue_without_discount` | `double precision` | no | Amount before discount when 1C provides it. |
| `channel` | `varchar` | no | Sales channel, usually `offline`. |
| `raw_data` | `jsonb` | no | Original 1C payload for diagnostics. |
| `synced_at` | `timestamp with time zone` | no | Time when the row was synced. |
| `sync_batch_id` | `varchar` | no | Sync batch id from `OneCSalesSyncService`. |
| `created_at` | `timestamp with time zone` | no | Row creation time. |
| `updated_at` | `timestamp with time zone` | no | Row update time. |
| `product_name` | `varchar` | no | Product name at sale time or enriched from catalog. |
| `product_article` | `varchar` | no | Product article/vendor code. |
| `product_category` | `varchar` | no | Normalized/derived product category. |
| `product_brand` | `varchar` | no | Normalized/derived brand. |
| `product_type` | `varchar` | no | Product type if available. |
| `cost_price` | `double precision` | no | Cost price if available. |
| `margin` | `double precision` | no | Margin if available. |

### Indexes and constraints

Important indexes:

- Primary key: `sales_records_pkey` on `id`.
- Unique partial index: `ix_sales_records_external_id` on `external_id` where it is not null.
- Date/store/customer/product indexes:
  - `ix_sales_records_sale_date`
  - `ix_sales_records_date_store`
  - `ix_sales_records_date_customer`
  - `ix_sales_records_date_product`
- Lookup indexes:
  - `ix_sales_records_document_id`
  - `ix_sales_records_store_id`
  - `ix_sales_records_customer_id`
  - `ix_sales_records_product_id`
  - `ix_sales_records_product_article`
  - `ix_sales_records_product_brand`
  - `ix_sales_records_product_category`
  - `ix_sales_records_product_type`
  - `ix_sales_records_channel`
  - `ix_sales_records_sync_batch_id`
  - `ix_sales_records_synced_at`

There are no foreign keys from `sales_records` to `users`, `stores`, or
`products`; the table stores 1C external keys and joins to local tables at query
time.

### How `sales_records` is updated

Main service: `backend/app/services/onec_sales_sync_service.py`.

Key methods:

- `OneCSalesSyncService.sync_period(start_date, end_date, incremental=True|False)`
- `OneCSalesSyncService.sync_incremental(days_back=...)`
- `OneCSalesSyncService.sync_full_period(start_date, end_date)`

Scheduled/entry points:

- `backend/app/services/onec_sales_sync_scheduler.py`
  - Runs the recent 1C sales sync loop.
  - Environment controls include `ONEC_SALES_SYNC_ENABLED`,
    `ONEC_SALES_SYNC_INTERVAL_MINUTES`, and `ONEC_SALES_SYNC_DAYS_BACK`.
- `backend/scripts/sync_sales_nightly.py`
  - Nightly script. Syncs the last seven days incrementally and then yesterday
    fully.
- `backend/app/api/analytics.py`
  - Contains manual/admin sync endpoints that call `OneCSalesSyncService`.
- Historical/import helpers:
  - `backend/scripts/import_sales_history_from_excels.py`
  - `backend/import_historical_sales_from_excel.py`
  - `backend/sync_all_1c_sales.py`
  - `backend/sync_all_1c_sales_via_api.py`

Important behavior in `sync_period`:

- Rows with `external_id` are upserted through PostgreSQL
  `ON CONFLICT DO UPDATE`.
- For check-based sources, old report/check rows for the period may be cleaned
  before inserting new check lines.
- Product fields are enriched from `products` when possible.
- Daily metrics are aggregated after the sync.
- Preferred customer store fields are refreshed for affected users.
- `purchase_history` is refreshed from `sales_records` at the end of the sync.

## `purchase_history`

Model: `backend/app/models/purchase_history.py`.

Database table: `purchase_history`.

### Columns

| Column | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | `uuid` | yes | Local purchase-history row id. |
| `user_id` | `uuid` | yes | Local customer id, foreign key to `users.id`. |
| `purchase_date` | `timestamp with time zone` | yes | Purchase timestamp. |
| `document_id_1c` | `varchar` | no | 1C receipt/document id. |
| `store_id_1c` | `varchar` | no | 1C store/warehouse key. |
| `product_id` | `uuid` | no | Local product UUID, foreign key to `products.id`. |
| `product_id_1c` | `varchar` | no | 1C product/nomenclature key. |
| `product_name` | `varchar` | no | Product name at purchase time. |
| `quantity` | `integer` | yes | Quantity normalized for customer history. |
| `price` | `integer` | no | Unit price in kopecks. |
| `total_amount` | `integer` | yes | Total amount in kopecks. |
| `category` | `varchar` | no | Product category used by CRM/customer analytics. |
| `brand` | `varchar` | no | Product brand used by CRM/customer analytics. |
| `sync_metadata` | `json` | no | Source metadata. Rows refreshed from `sales_records` include `source = sales_records`. |
| `created_at` | `timestamp with time zone` | no | Row creation time. |
| `product_article` | `varchar` | no | Product article/vendor code. |

### Indexes and constraints

Important indexes:

- Primary key: `purchase_history_pkey` on `id`.
- Foreign keys:
  - `purchase_history_user_id_fkey` references `users(id)`.
  - `purchase_history_product_id_fkey` references `products(id)`.
- Unique key:
  - `uq_purchase_history_unique` on
    `user_id`, `COALESCE(document_id_1c, '')`, `COALESCE(product_id_1c, '')`,
    and UTC purchase date.
- Lookup indexes:
  - `ix_purchase_history_user_id`
  - `ix_purchase_history_user_date`
  - `ix_purchase_history_purchase_date`
  - `ix_purchase_history_document_1c`
  - `ix_purchase_history_document_id_1c`
  - `ix_purchase_history_product_1c`
  - `ix_purchase_history_product_article`
  - `ix_purchase_history_product_id`

Tables that reference `purchase_history`:

- `loyalty_transactions.related_purchase_id`
- `referral_attributions.first_purchase_id`
- `referral_commissions.purchase_id`

### How `purchase_history` is updated

Current preferred path:

1. 1C sales are loaded into `sales_records`.
2. `OneCSalesSyncService.refresh_purchase_history_from_sales_records(start_date, end_date)`
   matches `sales_records.customer_id` to `users.customer_id_1c`.
3. Matching rows update existing `purchase_history` records.
4. Missing rows are inserted.
5. Product links are backfilled via `SalesProductLinkService`.
6. CRM interaction attribution is refreshed for affected users.

The refresh step is called automatically at the end of
`OneCSalesSyncService.sync_period()`.

Legacy/direct update paths still exist:

- `CustomerSyncService.sync_purchase_history()`
  - Fetches purchases per customer from 1C customer APIs.
  - Creates/updates `PurchaseHistory` directly.
  - Also recalculates customer metrics, product links, and CRM attribution.
- Older one-off scripts:
  - `backend/import_1c_purchases.py`
  - `backend/sync_customer_only.py`
  - `backend/sync_customer_correct.py`
  - customer-specific maintenance scripts under `backend/`.

Prefer the `sales_records` refresh path for fresh/current 1C receipt data because
it keeps sales analytics and customer history aligned.

## Synchronization flow

```text
1C sales API / files
        |
        v
OneCSalesSyncService.sync_period()
        |
        v
sales_records
        |
        | enrich products, aggregate sales metrics, refresh preferred store
        v
refresh_purchase_history_from_sales_records()
        |
        v
purchase_history
        |
        | backfill product links, update CRM interaction attribution
        v
CRM / customer profile / segmentation / loyalty / referrals
```

## Service usage map

### Main users of `sales_records`

The following modules use `sales_records` for sales, product, inventory, or
director analytics:

- `backend/app/api/analytics.py`
- `backend/app/api/inventory.py`
- `backend/app/api/agent_interactions.py`
- `backend/app/api/director.py`
- `backend/app/api/stores.py`
- `backend/app/services/onec_sales_sync_service.py`
- `backend/app/services/onec_sales_sync_scheduler.py`
- `backend/app/services/product_analytics_service.py`
- `backend/app/services/inventory_control_service.py`
- `backend/app/services/seller_kpi_service.py` and seller KPI helpers
- `backend/app/agents/director_data_service.py`
- `backend/app/agents/director_agent.py`
- Historical/import/maintenance scripts for sales records

Typical use cases:

- Revenue by day/store/channel.
- Distinct receipt count through `document_id`.
- Product/category/brand sales.
- Inventory sell-through.
- Director dashboards and diagnostics.
- Preferred store refresh by recent sales.

### Main users of `purchase_history`

The following modules use `purchase_history` for customer-specific purchase
logic:

- `backend/app/services/customer_sync_service.py`
- `backend/app/services/crm_task_service.py`
- `backend/app/services/crm_interaction_attribution_service.py`
- `backend/app/services/communication_service.py`
- `backend/app/services/loyalty_service.py`
- `backend/app/services/referral_service.py`
- `backend/app/services/customer_analytics_service.py`
- `backend/app/api/customer_segmentation.py`
- `backend/app/api/communication.py`
- `backend/app/api/director.py` customer purchase history endpoint
- `backend/app/api/agent_interactions.py` customer/brand history context
- `backend/app/agents/communication_agent.py`
- `backend/app/agents/director_agent.py`
- Customer cleanup/deletion services and referral SQL tables

Typical use cases:

- CRM campaign attribution by customer and contact window.
- Seller CRM purchase-after-touch analytics.
- Customer segmentation by purchase store, brand, date, frequency, spend.
- Communication personalization from purchase history.
- Loyalty and referral purchase references.
- Customer profile metrics such as total spent, average check, last purchase,
  favorite categories/brands/products.

## CRM attribution rules

CRM analytics currently reads `purchase_history`, not `sales_records`.

Important code paths:

- `CrmTaskService.campaign_analytics()`
- `CrmTaskService._append_sms_campaign_analytics()`
- `CrmTaskService._message_window_purchases()`
- `CrmTaskService.attribute_purchases()`
- `CrmInteractionAttributionService.update_purchase_conversions()`

For SMS Aero imports, a purchase is attributed only when:

1. The SMS `customer_messages.user_id` matches `purchase_history.user_id`.
2. The purchase date is after `customer_messages.sent_at`.
3. The purchase date is within the attribution window, usually 14 days.
4. The purchase passes `is_analytics_eligible_product()` filters.

If sales exist in `sales_records` but analytics shows zero, check these in order:

1. Do recent rows exist in `purchase_history`?
2. Do those rows have local `user_id` values?
3. Do buying users overlap with campaign/message recipients?
4. Are dates inside the attribution window?
5. Were products filtered out as non-eligible, such as packaging or certificates?

Example from 2026-08-01:

- `sales_records` contained fresh sales after the SMS campaign.
- `purchase_history` had no rows after 2026-07-28, so CRM showed zero.
- After `refresh_purchase_history_from_sales_records()`, `purchase_history`
  received 43 rows for 6 users and 7 checks.
- Campaign `3=2 Симферополь` still showed zero because the buying users did not
  overlap with that campaign's recipients by `user_id` or phone.

## Known caveats

### Anonymous 1C sales cannot be attributed to customers

Rows where `sales_records.customer_id` is empty or
`00000000-0000-0000-0000-000000000000` cannot be linked to `users.id` by the
current bridge. They remain usable for store/product revenue analytics, but not
for CRM attribution or customer history.

### Amount units differ

`sales_records.revenue` is rubles. `purchase_history.total_amount` and
`purchase_history.price` are kopecks.

When copying or comparing values:

- `purchase_history.total_amount = ROUND(sales_records.revenue * 100)`
- UI/API fields named `*_kopecks` expect `purchase_history` units.

### Distinct checks vs line rows

Both tables can contain multiple rows per receipt because each product line may
be a row.

Use distinct document ids for purchase/check count:

- `sales_records`: `COUNT(DISTINCT document_id)`
- `purchase_history`: `COUNT(DISTINCT document_id_1c)`

### Product fields are partly denormalized

Both tables store product name/article/category/brand snapshots. Product links
may also be resolved against `products`.

Do not assume `product_id` means the same thing:

- `sales_records.product_id` is a 1C product key string.
- `purchase_history.product_id` is a local `products.id` UUID.
- `purchase_history.product_id_1c` is the 1C product key string.

### `purchase_history` is a view-like table, not the raw receipt source

It has its own foreign keys and is referenced by loyalty/referral records.
Do not drop, truncate, or rebuild it without a migration plan for dependent
tables.

## Recommended usage for new work

Use `sales_records` when building:

- sales dashboards;
- store revenue reports;
- product, brand, category analytics;
- inventory/sell-through logic;
- 1C sync diagnostics;
- receipt-level or line-level operational reports.

Use `purchase_history` when building:

- customer profile purchase history;
- CRM campaign attribution;
- seller follow-up analytics;
- customer segmentation by purchase behavior;
- loyalty and referral features;
- communication personalization.

If a feature needs both detailed receipt accuracy and local customer identity,
start from `sales_records`, join to `users` by `users.customer_id_1c`, then decide
whether the result should also be materialized into `purchase_history`.

## Operational checks

### Check latest dates

```sql
SELECT MAX(sale_date) FROM sales_records;
SELECT MAX(purchase_date) FROM purchase_history;
```

If `sales_records` is fresh but `purchase_history` is stale, run or inspect:

```python
await OneCSalesSyncService(db).refresh_purchase_history_from_sales_records(start_date, end_date)
```

### Check bridge coverage for a period

```sql
SELECT
    COUNT(*) AS sales_rows_with_user,
    COUNT(DISTINCT u.id) AS users
FROM sales_records sr
JOIN users u ON u.customer_id_1c = sr.customer_id
WHERE sr.sale_date >= :start_date
  AND sr.sale_date <= :end_date;
```

### Check rows missing from `purchase_history`

```sql
SELECT COUNT(*) AS missing_purchase_history_rows
FROM sales_records sr
JOIN users u ON u.customer_id_1c = sr.customer_id
LEFT JOIN purchase_history ph
  ON ph.user_id = u.id
 AND COALESCE(ph.document_id_1c, '') = COALESCE(sr.document_id, '')
 AND COALESCE(ph.product_id_1c, '') = COALESCE(sr.product_id, '')
 AND (ph.purchase_date AT TIME ZONE 'UTC')::date = (sr.sale_date AT TIME ZONE 'UTC')::date
WHERE sr.sale_date >= :start_date
  AND sr.sale_date <= :end_date
  AND sr.customer_id IS NOT NULL
  AND sr.customer_id <> ''
  AND sr.customer_id <> '00000000-0000-0000-0000-000000000000'
  AND ph.id IS NULL;
```

### Check campaign recipient/purchaser overlap

```sql
WITH campaign_users AS (
    SELECT DISTINCT user_id
    FROM customer_messages
    WHERE payload->>'campaign_id' = :campaign_id
),
buyers AS (
    SELECT DISTINCT user_id
    FROM purchase_history
    WHERE purchase_date >= :campaign_start
      AND purchase_date <= :campaign_start + INTERVAL '14 days'
)
SELECT COUNT(*) AS overlap_users
FROM campaign_users
JOIN buyers USING (user_id);
```

## Change log

2026-08-01:

- Confirmed `sales_records` had fresh sales while `purchase_history` was stale.
- Added `OneCSalesSyncService.refresh_purchase_history_from_sales_records()`.
- Connected the refresh step to `OneCSalesSyncService.sync_period()`.
- Backfilled recent post-campaign sales into `purchase_history`.
- Kept CRM/customer services on `purchase_history` to avoid a broad, risky
  rewrite.
