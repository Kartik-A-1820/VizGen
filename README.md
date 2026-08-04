# VizGen

A local, self-hosted **image generation and instruction-editing** server for a 4 GB GPU target.

VizGen runs a React UI, a FastAPI queue/orchestration backend, and a headless ComfyUI engine. The product is image-only and designed for the GTX 1650 Ti 4 GB target.

## Features

- **Generate**: text-to-image through a registry-driven model dropdown.
- **Edit**: image + natural-language instruction to edited image, routed internally to FLUX.1 Kontext.
- **Enhance**: optional local Qwen2.5 prompt/negative-prompt enhancer on CPU.
- **Upscale**: optional RealESRGAN x4 post-processing.
- **Staged low-VRAM pipeline**: enhance, generate/edit, and upscale run sequentially with ComfyUI `/free` between stages.
- **Live progress**: stage, message, progress, ETA, queue status, and gallery.

## Hardware Target

Built for Windows 11 with NVIDIA GTX 1650 Ti 4 GB, 16 GB RAM, CUDA 11.8, and torch 2.7.1+cu118. Larger GPUs will run faster, but this repo is designed around strict 4 GB VRAM discipline: GGUF models, low-VRAM ComfyUI, and one model loaded at a time.

## Quick Start

Prerequisites: Python 3.10 or 3.11, Git, Node.js/npm, and recent NVIDIA drivers.

```bat
git clone https://github.com/Kartik-A-1820/VizGen.git
cd VizGen

setup.bat
launch.bat
```

Open `http://localhost:5173`.

`setup.bat` installs dependencies, clones ComfyUI, installs image-model support, downloads auxiliary models, and calls `scripts\download_image_models.py` for the image/edit model set. Some model downloads may require a Hugging Face token.

## Architecture

```text
Web UI (React/Vite, :5173)
      |
FastAPI backend (:8000) -- SQLite queue -- staged worker
      |                    enhance -> generate/edit -> upscale
      |                    /free between stages
ComfyUI engine (:8188, --lowvram)
Qwen2.5-1.5B CPU prompt enhancer
```

## Key Paths

| Component | Path |
|---|---|
| Backend API and worker | `backend/app/` |
| Model registry | `backend/models_registry.yaml` |
| ComfyUI workflows | `backend/workflows/` |
| Frontend | `frontend/` |
| Setup/download scripts | `scripts/` |
| Plan and status | `plan.md` |

Model weights, the ComfyUI clone, Python venv, node modules, generated outputs, and SQLite data are excluded from git.

## Development

Run pieces individually after setup:

```bat
.venv\Scripts\python.exe engine\comfyui\main.py --listen 127.0.0.1 --port 8188 --lowvram --disable-auto-launch
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

See `plan.md` for the current image-only roadmap and per-track responsibilities.
