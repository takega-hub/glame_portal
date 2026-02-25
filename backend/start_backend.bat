@echo off
cd /d %~dp0
set PYTHONPATH=%~dp0
call venv\Scripts\activate.bat
REM IMPORTANT (Windows):
REM When using psycopg3 async driver, Uvicorn reload mode can create the asyncio event loop
REM before importing the app, which prevents switching to WindowsSelectorEventLoopPolicy and causes:
REM   "Psycopg cannot use the 'ProactorEventLoop' to run in async mode"
REM
REM So we start via start_server.py which sets the event loop policy before Uvicorn runs.
venv\Scripts\python.exe start_server.py
