# Скрипт запуска backend
Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot
.\venv\Scripts\Activate.ps1

# IMPORTANT (Windows):
# When using psycopg3 async driver, Uvicorn reload mode can create the asyncio event loop
# *before* importing the app, which prevents our code from switching to
# WindowsSelectorEventLoopPolicy and causes:
#   "Psycopg cannot use the 'ProactorEventLoop' to run in async mode"
#
# So we start via start_server.py which sets the event loop policy before Uvicorn runs.
.\venv\Scripts\python.exe .\start_server.py
