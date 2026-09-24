ALTER TABLE app_promotions
  ADD COLUMN IF NOT EXISTS discount_kind VARCHAR(64) NOT NULL DEFAULT 'none',
  ADD COLUMN IF NOT EXISTS is_cart_discount BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS group_size INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS discounted_items_per_group INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS discounted_item_price INTEGER NOT NULL DEFAULT 100,
  ADD COLUMN IF NOT EXISTS discount_config JSONB;

UPDATE app_promotions
SET
  discount_kind = COALESCE(NULLIF(discount_kind, ''), 'none'),
  group_size = COALESCE(NULLIF(group_size, 0), 3),
  discounted_items_per_group = COALESCE(NULLIF(discounted_items_per_group, 0), 1),
  discounted_item_price = COALESCE(discounted_item_price, 100);
