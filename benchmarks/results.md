# Benchmark results — image-only pivot (Track A)

Hardware: GTX 1650 Ti 4GB · 16GB RAM · torch 2.7.1+cu118 · ComfyUI `--lowvram`

## Aux (verified)

| Tool | Model | Status |
|------|--------|--------|
| Prompt enhance | Qwen2.5-1.5B-Instruct CPU | ✅ works (`scripts/prompt_enhance.py`) |
| Super-res ×4 | RealESRGAN_x4plus | ✅ works via `scripts/upscale_image.py` (512→2048); ComfyUI node broken under lowvram — backend uses standalone script |

## Weights on disk (Track A)

| File | ~MB | Role |
|------|-----|------|
| `models/unet/flux1-kontext-dev-Q3_K_S.gguf` | 4983 | Edit (Kontext) |
| `models/text_encoders/clip_l.safetensors` | 234 | Flux TE |
| `models/text_encoders/t5xxl_fp8_e4m3fn.safetensors` | 4667 | Flux TE (CPU) |
| `models/vae/ae.safetensors` | 319 | Shared Flux/Z-Image VAE |
| `models/llm/Qwen2.5-1.5B-Instruct/` | ~2944 | Enhance |
| `models/upscale_models/RealESRGAN_x4plus.pth` | 64 | Upscale |
| `models/unet/z_image_turbo-Q4_K_M.gguf` | present | Primary generate |
| `models/text_encoders/qwen_3_4b_fp8_mixed.safetensors` | present | Z-Image TE |
| `models/unet/flux1-dev-Q4_K_S.gguf` | 8100 | Max-quality generate |
| `models/unet/qwen-image-Q4_K_M.gguf` | 12460 | Qwen-Image generate |
| `models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` | 8950 | Qwen-Image TE |
| `models/vae/qwen_image_vae.safetensors` | 242 | Qwen-Image VAE |
| `models/loras/Qwen-Image-Lightning-8steps-V1.0.safetensors` | 1620 | Qwen-Image Lightning LoRA |

Wan2.2 video weights: **removed** (pivot).

## Workflows authored

| File | Task |
|------|------|
| `backend/workflows/z_image_turbo_t2i_api.json` | generate |
| `backend/workflows/z_image_turbo_generate_api.json` | generate |
| `backend/workflows/flux_dev_generate_api.json` | generate |
| `backend/workflows/qwen_image_lightning_generate_api.json` | generate |
| `backend/workflows/flux_kontext_edit_api.json` | edit |
| `backend/workflows/upscale_realesrgan_x4_api.json` | reference only — runtime uses script |

## Smoke matrix

| Model | Mode | Quant | Res | Steps | VRAM peak | Wall | OK | Notes |
|-------|------|-------|-----|-------|-----------|------|-----|-------|
| Z-Image Turbo | generate | Q4_K_M | 512² | 8 | ~0.8GB idle after | **~495 s** | **yes** | `engine/comfyui/output/z_image_turbo_00001_.png` — primary path |
| FLUX Kontext | edit | Q3_K_S | auto-scale | 20 | *not smoked yet* | | | weights+workflow ready; T5 on CPU will be slow |

## Proposed `models_registry.yaml` entries (Track B merges)

```yaml
  - id: z-image-turbo
    label: Z-Image Turbo
    family: Z-Image
    model_name: Z-Image-Turbo
    task: generate
    tier: fast
    engine: comfyui
    quant: Q4_K_M
    vram_tier: 4gb-lowvram
    workflow: z_image_turbo_t2i_api.json
    defaults:
      width: 512
      height: 512
      steps: 8
      cfg: 1.0
      sampler: euler
      scheduler: simple
      seed: -1
    launch_flags: ["--lowvram"]
    paths:
      unet: models/unet/z_image_turbo-Q4_K_M.gguf
      text_encoder: models/text_encoders/qwen_3_4b_fp8_mixed.safetensors
      vae: models/vae/ae.safetensors
    enabled: true   # after smoke OK
    ui_note: "Primary few-step generate model for 4GB."

  - id: flux-kontext-dev
    label: FLUX.1 Kontext dev
    family: FLUX.1
    model_name: FLUX.1-Kontext-dev
    task: edit
    tier: edit
    engine: comfyui
    quant: Q3_K_S
    vram_tier: 4gb-heavy-offload
    workflow: flux_kontext_edit_api.json
    defaults:
      width: 1024
      height: 1024
      steps: 20
      cfg: 1.0
      sampler: euler
      scheduler: simple
      seed: -1
    launch_flags: ["--lowvram", "--cpu-vae"]
    paths:
      unet: models/unet/flux1-kontext-dev-Q3_K_S.gguf
      clip_l: models/text_encoders/clip_l.safetensors
      t5: models/text_encoders/t5xxl_fp8_e4m3fn.safetensors
      vae: models/vae/ae.safetensors
    enabled: true   # after smoke OK
    ui_note: "Instruction image editing. Slow on 4GB (T5 on CPU)."
```

## Codex generate-model expansion smoke (2026-08-04)

Prompt: `a crisp product photo of a red ceramic mug on a wooden desk, soft daylight, sharp focus`.

| Model | Workflow | Res | Steps | VRAM peak | Wall | OK | Output |
|---|---|---|---:|---:|---:|---|---|
| Qwen-Image Lightning | `qwen_image_lightning_generate_api.json` | 512x512 | 4 | 2793 MB | 928.6 s | yes | `engine/comfyui/output/qwen_image_lightning_00001_.png` |
| FLUX.1-dev | `flux_dev_generate_api.json` | 512x512 | 4 | 2995 MB | 561.0 s | yes | `engine/comfyui/output/flux_dev_00001_.png` |

Full smoke details: `benchmarks/generate_model_smoke.md`. The full 512/768/1024 matrix for Qwen-Image and FLUX.1-dev is expected to take hours on 4GB/16GB and should be run as an unattended long benchmark pass.

## Backend note (upscale)

`comfy_client.run_upscale` must call `scripts/upscale_image.py` (device-safe). Worker should allow upscale for modes `generate` and `edit`.
