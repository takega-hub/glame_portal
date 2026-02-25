"""
Скрипт создания таблиц для внешней аналитики
"""
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    exit(1)

# Парсим URL
from urllib.parse import urlparse
parsed = urlparse(DATABASE_URL)

SQL = """
-- Create social_media_metrics table
CREATE TABLE IF NOT EXISTS social_media_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(64) NOT NULL,
    metric_type VARCHAR(64) NOT NULL,
    post_id VARCHAR(255),
    date TIMESTAMP WITH TIME ZONE NOT NULL,
    value FLOAT NOT NULL DEFAULT 0.0,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    views INTEGER,
    reach INTEGER,
    engagement FLOAT,
    meta_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for social_media_metrics
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_platform ON social_media_metrics(platform);
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_metric_type ON social_media_metrics(metric_type);
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_date ON social_media_metrics(date);
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_platform_date ON social_media_metrics(platform, date);
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_platform_type ON social_media_metrics(platform, metric_type);
CREATE INDEX IF NOT EXISTS ix_social_media_metrics_platform_post ON social_media_metrics(platform, post_id);

-- Create sales_metrics table
CREATE TABLE IF NOT EXISTS sales_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date TIMESTAMP WITH TIME ZONE NOT NULL,
    order_id VARCHAR(255),
    store_id UUID REFERENCES stores(id),
    channel VARCHAR(64),
    revenue FLOAT NOT NULL DEFAULT 0.0,
    order_count INTEGER NOT NULL DEFAULT 0,
    items_sold INTEGER NOT NULL DEFAULT 0,
    average_order_value FLOAT NOT NULL DEFAULT 0.0,
    returns_count INTEGER DEFAULT 0,
    returns_amount FLOAT DEFAULT 0.0,
    meta_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for sales_metrics
CREATE INDEX IF NOT EXISTS ix_sales_metrics_date ON sales_metrics(date);
CREATE INDEX IF NOT EXISTS ix_sales_metrics_store_id ON sales_metrics(store_id);
CREATE INDEX IF NOT EXISTS ix_sales_metrics_channel ON sales_metrics(channel);
CREATE INDEX IF NOT EXISTS ix_sales_metrics_date_channel ON sales_metrics(date, channel);
CREATE INDEX IF NOT EXISTS ix_sales_metrics_date_store ON sales_metrics(date, store_id);
CREATE INDEX IF NOT EXISTS ix_sales_metrics_channel_date ON sales_metrics(channel, date);
"""

try:
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path[1:],
        user=parsed.username,
        password=parsed.password
    )
    
    cursor = conn.cursor()
    
    print("[INFO] Creating analytics tables...")
    cursor.execute(SQL)
    conn.commit()
    
    print("[OK] Analytics tables created successfully")
    
    # Проверяем созданные таблицы
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('social_media_metrics', 'sales_metrics')
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f"[INFO] Created tables: {', '.join([t[0] for t in tables])}")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    exit(1)
