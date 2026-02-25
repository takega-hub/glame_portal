#!/usr/bin/env python
"""
Скрипт для запуска seeds данных
"""
from app.database.seeds import run_seeds

if __name__ == "__main__":
    print("Running seeds...")
    run_seeds()
    print("Seeds completed!")
