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

## Models

The dropdown is driven entirely by `backend/models_registry.yaml`.

| Task | Model | Notes |
|---|---|---|
| Generate (default) | **Z-Image Turbo** (6B, GGUF) | fastest + highest verified quality on 4 GB; few-step |
| Generate | Qwen-Image Lightning (GGUF) | quality option, 4–8 step |
| Generate | FLUX.1-dev (GGUF Q4) | max prompt-adherence, slow |
| Edit | **FLUX.1 Kontext** (12B, GGUF) | instruction editing; slow on 4 GB (~15–40 min/edit) |
| Enhance | Qwen2.5-1.5B (CPU) | prompt + negative rewriting |
| Upscale | RealESRGAN ×4 | post-process super-resolution |

## Benchmarks

On the 4 GB target, **Z-Image Turbo is the pick** — **~3–3.5 min at 512–768²** (~80 s once the encoder is warm) with near-SOTA photorealism. **768² is the sweet spot**; 1024² pushes VRAM to 94 % and thrashes (~7 min). Editing (FLUX Kontext) works but is a **slow tier** (~15–40 min/edit — the 12 B model exceeds 4 GB). Full numbers and methodology in **[BENCHMARKS.md](BENCHMARKS.md)**.

## Quick Start

Prerequisites: Python 3.10 or 3.11, Git, Node.js/npm, and recent NVIDIA drivers.

```bat
git clone https://github.com/Kartik-A-1820/VizGen.git
cd VizGen

setup.bat
launch.bat
```

Open `http://localhost:5173`.

`setup.bat` installs dependencies, clones ComfyUI, installs image-model support, downloads auxiliary models, and calls `scripts\download_image_models.py` for the image/edit model set (~15–20 GB). It **prompts you to paste a free [Hugging Face token](https://huggingface.co/settings/tokens)** to speed up downloads — press Enter to skip and download anonymously (slower).

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

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design, mermaid diagrams, and the reasoning behind every 4 GB optimization.

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
