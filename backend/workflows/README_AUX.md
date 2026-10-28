# Auxiliary image-processing stages

Run commands from the repository root after the full model environment is prepared. See the [root setup](../../README.md).

## Prompt enhancement

The worker starts `scripts/prompt_enhance.py` in a CPU subprocess, then releases that process before generation. The default model directory is `models/llm/Qwen2.5-1.5B-Instruct`.

```bash
python scripts/prompt_enhance.py "a city street at dusk" --mode image --json
```

The job request uses `enhance_prompt: true`. Model output can change the requested wording; inspect the enhanced prompt when evaluating generation.

## Upscaling

The worker releases the generation model and calls the Comfy client upscaling path for the generated image. The standalone `scripts/upscale_image.py` utility is also available:

```bash
python scripts/upscale_image.py in.png -o out_x4.png --device auto
```

It requires `models/upscale_models/RealESRGAN_x4plus.pth`. Use `scripts/download_aux_models.py` for auxiliary artifacts after checking their terms and storage requirements.

The job request uses `upscale: true`; the current worker accepts generation and edit modes. The pipeline is optional enhancement, core generation/editing, then optional upscaling. Check the active workflow and current ComfyUI/custom-node compatibility rather than relying on old video-model names or earlier low-VRAM observations.

For changes, report engine/custom-node revisions, model files, resolution, stage timings, and a verified saved output. See [CONTRIBUTING.md](../../CONTRIBUTING.md).
