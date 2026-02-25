#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания таблицы customer_messages (история сгенерированных сообщений).
Запустите один раз при первом развёртывании или после обновления.
"""
import asyncio
from sqlalchemy import text
from app.database.connection import AsyncSessionLocal


async def add_customer_messages_table():
    async with AsyncSessionLocal() as session:
        try:
            check = await session.execute(text("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'customer_messages'
            """))
            if check.scalar_one_or_none():
                print("Таблица 'customer_messages' уже существует.")
                return
            await session.execute(text("""
                CREATE TABLE customer_messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    message TEXT NOT NULL,
                    cta TEXT,
                    segment VARCHAR(20),
                    event_type VARCHAR(100),
                    event_brand VARCHAR(255),
                    event_store VARCHAR(255),
                    payload JSONB,
                    status VARCHAR(20) NOT NULL DEFAULT 'new',
                    sent_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX ix_customer_messages_user_id ON customer_messages(user_id);
                CREATE INDEX ix_customer_messages_status ON customer_messages(status);
                CREATE INDEX ix_customer_messages_user_created ON customer_messages(user_id, created_at);
            """))
            await session.commit()
            print("Таблица 'customer_messages' успешно создана.")
        except Exception as e:
            await session.rollback()
            print(f"Ошибка: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(add_customer_messages_table())
