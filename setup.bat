@echo off
REM ============================================================================
REM  VizGen — one-time setup. Run this ONCE.
REM  Creates the Python venv, installs all dependencies, clones the ComfyUI
REM  engine + custom nodes, downloads model weights, and installs the web UI.
REM  Re-running is safe: existing steps are skipped.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo(
echo ==========================================================
echo   VizGen setup  (this downloads several GB of weights)
echo ==========================================================
echo(

REM --- prerequisites -------------------------------------------------------
where python >nul 2>&1 || ( echo [ERROR] Python 3.10/3.11 not found on PATH. & exit /b 1 )
where git    >nul 2>&1 || ( echo [ERROR] git not found on PATH. & exit /b 1 )
where npm    >nul 2>&1 || ( echo [ERROR] Node.js/npm not found on PATH. & exit /b 1 )

set "PY=.venv\Scripts\python.exe"

REM --- Hugging Face token (for fast model downloads) -----------------------
REM Model weights come from Hugging Face. A free access token makes downloads
REM much faster and avoids anonymous rate limits. Asked once, used below.
if defined HF_TOKEN goto :hf_ready
echo(
echo   This setup downloads multiple large model families and auxiliary weights.
echo   An optional access token may be needed for selected model access.
echo   Create one at:  https://huggingface.co/settings/tokens
echo(
set /p "HF_TOKEN=  Paste your Hugging Face token (or press Enter to skip): "
:hf_ready
if defined HF_TOKEN (
  echo   [ok] Hugging Face token set for this setup.
) else (
  echo   [warn] No token entered - downloads will use anonymous access where allowed.
)
echo(

REM --- 1. virtual environment ---------------------------------------------
if not exist "%PY%" (
  echo [1/8] Creating virtual environment (.venv) ...
  python -m venv .venv || ( echo [ERROR] venv creation failed. & exit /b 1 )
) else (
  echo [1/8] Virtual environment already exists — skipping.
)

echo [2/8] Upgrading pip ...
"%PY%" -m pip install --upgrade pip wheel setuptools

REM --- 2. PyTorch (CUDA 11.8 — GTX 16xx / Turing friendly) ------------------
echo [3/8] Installing PyTorch (CUDA 11.8) ...
"%PY%" -c "import torch" 2>nul && (
  echo       torch already installed — skipping.
) || (
  "%PY%" -m pip install torch==2.7.1+cu118 torchvision --index-url https://download.pytorch.org/whl/cu118 || ( echo [ERROR] torch install failed. & exit /b 1 )
)

REM --- 3. Python dependencies (backend + enhancer + engine helpers) --------
echo [4/8] Installing Python dependencies ...
"%PY%" -m pip install -r backend\requirements.txt
"%PY%" -m pip install transformers accelerate huggingface_hub safetensors sentencepiece gguf av imageio-ffmpeg

REM --- 4. ComfyUI engine + custom nodes ------------------------------------
echo [5/8] Setting up ComfyUI engine ...
if not exist "engine\comfyui\main.py" (
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git engine\comfyui || ( echo [ERROR] ComfyUI clone failed. & exit /b 1 )
)
"%PY%" -m pip install -r engine\comfyui\requirements.txt
if not exist "engine\comfyui\custom_nodes\ComfyUI-GGUF" (
  git clone --depth 1 https://github.com/city96/ComfyUI-GGUF.git engine\comfyui\custom_nodes\ComfyUI-GGUF
  "%PY%" -m pip install -r engine\comfyui\custom_nodes\ComfyUI-GGUF\requirements.txt
)
REM --- 5. point ComfyUI at ./models ----------------------------------------
echo [6/8] Writing ComfyUI model paths ...
"%PY%" scripts\write_model_paths.py

REM --- 6. download model weights (large) -----------------------------------
echo [7/8] Downloading model weights (image gen + editing + aux) ...
echo       (set HF_TOKEN env var first for faster Hugging Face downloads)
"%PY%" scripts\download_image_models.py            || echo [WARN] image-model download had issues — re-run setup.bat to resume.
"%PY%" scripts\download_aux_models.py              || echo [WARN] aux (Qwen/RealESRGAN) download had issues — re-run setup.bat to resume.

REM --- 7. web UI -----------------------------------------------------------
echo [8/8] Installing web UI dependencies ...
pushd frontend
call npm install
popd

echo(
echo ==========================================================
echo   Setup complete.  Start everything with:  launch.bat
echo ==========================================================
endlocal
