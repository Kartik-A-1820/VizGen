@echo off
REM ============================================================================
REM  VizGen — launch everything. Run this each time you want to use VizGen.
REM  Opens three windows (ComfyUI engine, backend API, web UI) and your browser.
REM  Requires setup.bat to have been run once first.
REM ============================================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Not set up yet. Run setup.bat first.
  pause
  exit /b 1
)

echo Starting VizGen ...

REM 1) ComfyUI inference engine (GPU, low-VRAM mode) on :8188
start "VizGen - ComfyUI Engine" cmd /k .venv\Scripts\python.exe engine\comfyui\main.py --listen 127.0.0.1 --port 8188 --lowvram --disable-auto-launch

REM 2) Backend API + job queue on :8000
start "VizGen - Backend API" cmd /k .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

REM 3) Web UI (Vite dev server, proxies to backend) on :5173
start "VizGen - Web UI" cmd /k "cd frontend && npm run dev"

REM Give the services a moment, then open the browser
echo Waiting for services to come up ...
timeout /t 12 /nobreak >nul
start "" http://localhost:5173

echo(
echo VizGen is starting in three windows:
echo   - ComfyUI Engine : http://127.0.0.1:8188
echo   - Backend API    : http://127.0.0.1:8000
echo   - Web UI         : http://localhost:5173  (opened in your browser)
echo(
echo Close those windows to stop VizGen.
