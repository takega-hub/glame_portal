#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка что колонка email nullable"""
import os
import sys

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "5433"))
user = os.getenv("DB_USER", "glame_user")
password = os.getenv("DB_PASSWORD", "glame_password")
db_name = os.getenv("DB_NAME", "glame_db")

db_url = URL.create(
    drivername="postgresql+psycopg2",
    username=user,
    password=password,
    host=host,
    port=port,
    database=db_name,
)

engine = create_engine(db_url, echo=False)
conn = engine.connect()

result = conn.execute(text("""
    SELECT column_name, is_nullable 
    FROM information_schema.columns 
    WHERE table_name = 'users' AND column_name = 'email'
"""))

row = result.fetchone()
if row:
    print(f"Колонка email: nullable = {row[1]}")
    if row[1] == 'YES':
        print("OK: Колонка email может быть NULL - готово к синхронизации!")
    else:
        print("ERROR: Колонка email все еще NOT NULL")
else:
    print("ERROR: Колонка email не найдена")

conn.close()
