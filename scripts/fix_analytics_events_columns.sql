-- Добавить колонки из миграции 008_expand_analytics_events, если их нет
-- (после восстановления старого дампа без этих полей)
-- Запуск: docker exec -i glame_postgres psql -U glame_user -d glame_db < scripts/fix_analytics_events_columns.sql

ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS product_id UUID;
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS look_id UUID;
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS content_item_id UUID;
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS channel VARCHAR(64);
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS utm_source VARCHAR(255);
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(255);
ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS utm_campaign VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_analytics_events_user_id ON analytics_events (user_id);
CREATE INDEX IF NOT EXISTS ix_analytics_events_product_id ON analytics_events (product_id);
CREATE INDEX IF NOT EXISTS ix_analytics_events_look_id ON analytics_events (look_id);
CREATE INDEX IF NOT EXISTS ix_analytics_events_content_item_id ON analytics_events (content_item_id);
CREATE INDEX IF NOT EXISTS ix_analytics_events_channel ON analytics_events (channel);
CREATE INDEX IF NOT EXISTS ix_analytics_events_timestamp ON analytics_events (timestamp);
CREATE INDEX IF NOT EXISTS ix_analytics_events_event_type ON analytics_events (event_type);
CREATE INDEX IF NOT EXISTS ix_analytics_events_user_timestamp ON analytics_events (user_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_analytics_events_type_timestamp ON analytics_events (event_type, timestamp);
CREATE INDEX IF NOT EXISTS ix_analytics_events_channel_timestamp ON analytics_events (channel, timestamp);
