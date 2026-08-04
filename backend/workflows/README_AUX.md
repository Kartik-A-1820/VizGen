# Auxiliary tools — image product path

Video generation is **not** the product focus. Use **t2i** + optional enhance + optional x4 upscale.

## Prompt enhancement (CPU LLM)

| Item | Path |
|------|------|
| Model | `models/llm/Qwen2.5-1.5B-Instruct` |
| Script | `scripts/prompt_enhance.py` |
| API | `POST /api/jobs` with `"enhance_prompt": true` |
| UI | Generate page checkbox “Enhance prompt” |

Runs **before** Wan loads (worker calls ComfyUI `/free` first). Releases on process exit.

```text
.venv\Scripts\python.exe scripts\prompt_enhance.py "cyberpunk alley" --mode image --json
```

## Super-resolution x4 (RealESRGAN)

| Item | Path |
|------|------|
| Weights | `models/upscale_models/RealESRGAN_x4plus.pth` |
| Script | `scripts/upscale_image.py` (used by backend — **not** the broken ComfyUI node under `--lowvram`) |
| API | `POST /api/jobs` with `"upscale": true` (t2i only) |
| UI | Generate page checkbox “Upscale x4” (enabled for t2i) |

Runs **after** generation; worker unloads Wan first so VRAM is free.

```text
.venv\Scripts\python.exe scripts\upscale_image.py in.png -o out_x4.png --device auto
```

## Full image job pipeline (backend worker)

1. *(optional)* **enhance** — Qwen CPU expands prompt + negative  
2. **generate** — Wan2.2 T2I via ComfyUI  
3. *(optional)* **upscale** — RealESRGAN x4 standalone  

Download auxiliaries:

```text
.venv\Scripts\python.exe scripts\download_aux_models.py
```

## Note on ComfyUI upscale graph

`upscale_realesrgan_x4_api.json` is retained for reference only. Under `--lowvram` the native `ImageUpscaleWithModel` node hits CUDA/CPU weight mismatch; production path is `scripts/upscale_image.py`.
