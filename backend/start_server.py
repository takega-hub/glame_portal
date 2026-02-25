"""
Единая точка запуска backend на Windows.

Важно: psycopg3/async драйверы требуют WindowsSelectorEventLoopPolicy.

Запуск:
  backend\\venv\\Scripts\\python.exe backend\\start_server.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Устанавливаем PYTHONPATH на директорию backend, чтобы модуль app был доступен
backend_dir = Path(__file__).parent.absolute()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Устанавливаем переменную окружения PYTHONPATH для дочерних процессов
os.environ["PYTHONPATH"] = str(backend_dir)

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


def main() -> None:
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()

