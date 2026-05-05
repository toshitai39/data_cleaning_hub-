@echo off
REM Launch the FastAPI backend on port 8000.
cd /d "%~dp0"
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8765 --reload
