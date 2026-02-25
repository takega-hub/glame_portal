-- Создание таблицы knowledge_documents для истории загрузки базы знаний
-- Выполнить: psql -U glame_user -d glame_db -f create_knowledge_documents_table.sql
-- Или через Python: python create_knowledge_documents_table.py

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER,
    source VARCHAR(255),
    collection_name VARCHAR(100) NOT NULL DEFAULT 'brand_philosophy',
    total_items INTEGER NOT NULL DEFAULT 0,
    uploaded_items INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,
    vector_document_ids JSONB,
    document_metadata JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Создание индексов
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_filename ON knowledge_documents(filename);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status ON knowledge_documents(status);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_created_at ON knowledge_documents(created_at);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_collection_name ON knowledge_documents(collection_name);
