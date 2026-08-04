"""
Track A — download image-only pivot models (no video).

Priority:
  1. Z-Image Turbo GGUF (primary generate)
  2. FLUX.1 Kontext GGUF + flux encoders + ae VAE (edit)
  3. FLUX.1-dev GGUF (max-quality generate)
  4. Qwen-Image GGUF + Lightning LoRA (quality/few-step generate)

Usage:
  .venv\\Scripts\\python.exe scripts\\download_image_models.py
  .venv\\Scripts\\python.exe scripts\\download_image_models.py --z-image
  .venv\\Scripts\\python.exe scripts\\download_image_models.py --kontext
  .venv\\Scripts\\python.exe scripts\\download_image_models.py --flux-dev
  .venv\\Scripts\\python.exe scripts\\download_image_models.py --qwen-image
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

# (repo, remote, local_subdir, local_name)
ITEMS = {
    "z_image": [
        (
            "jayn7/Z-Image-Turbo-GGUF",
            "z_image_turbo-Q4_K_M.gguf",
            "unet",
            "z_image_turbo-Q4_K_M.gguf",
        ),
        (
            "jayn7/Z-Image-Turbo-GGUF",
            "z_image_turbo-Q3_K_S.gguf",
            "unet",
            "z_image_turbo-Q3_K_S.gguf",
        ),
        (
            "Comfy-Org/z_image_turbo",
            "split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors",
            "text_encoders",
            "qwen_3_4b_fp8_mixed.safetensors",
        ),
        (
            "Comfy-Org/z_image_turbo",
            "split_files/vae/ae.safetensors",
            "vae",
            "ae.safetensors",
        ),
    ],
    "kontext": [
        (
            "bullerwins/FLUX.1-Kontext-dev-GGUF",
            "flux1-kontext-dev-Q3_K_S.gguf",
            "unet",
            "flux1-kontext-dev-Q3_K_S.gguf",
        ),
        (
            "comfyanonymous/flux_text_encoders",
            "clip_l.safetensors",
            "text_encoders",
            "clip_l.safetensors",
        ),
        (
            "comfyanonymous/flux_text_encoders",
            "t5xxl_fp8_e4m3fn.safetensors",
            "text_encoders",
            "t5xxl_fp8_e4m3fn.safetensors",
        ),
        (
            "Comfy-Org/Lumina_Image_2.0_Repackaged",
            "split_files/vae/ae.safetensors",
            "vae",
            "ae.safetensors",
        ),
    ],
    "flux_dev": [
        (
            "city96/FLUX.1-dev-gguf",
            "flux1-dev-Q4_K_S.gguf",
            "unet",
            "flux1-dev-Q4_K_S.gguf",
        ),
        (
            "comfyanonymous/flux_text_encoders",
            "clip_l.safetensors",
            "text_encoders",
            "clip_l.safetensors",
        ),
        (
            "comfyanonymous/flux_text_encoders",
            "t5xxl_fp8_e4m3fn.safetensors",
            "text_encoders",
            "t5xxl_fp8_e4m3fn.safetensors",
        ),
        (
            "Comfy-Org/Lumina_Image_2.0_Repackaged",
            "split_files/vae/ae.safetensors",
            "vae",
            "ae.safetensors",
        ),
    ],
    "qwen_image": [
        (
            "city96/Qwen-Image-gguf",
            "qwen-image-Q4_K_M.gguf",
            "unet",
            "qwen-image-Q4_K_M.gguf",
        ),
        (
            "Comfy-Org/Qwen-Image_ComfyUI",
            "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "text_encoders",
            "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        ),
        (
            "Comfy-Org/Qwen-Image_ComfyUI",
            "split_files/vae/qwen_image_vae.safetensors",
            "vae",
            "qwen_image_vae.safetensors",
        ),
        (
            "lightx2v/Qwen-Image-Lightning",
            "Qwen-Image-Lightning-8steps-V1.0.safetensors",
            "loras",
            "Qwen-Image-Lightning-8steps-V1.0.safetensors",
        ),
    ],
}


def download_one(repo: str, remote: str, subdir: str, local_name: str) -> None:
    dest_dir = MODELS / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / local_name
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"[skip] {local_name} ({dest.stat().st_size // (1024**2)} MB)")
        return
    print(f"[dl] {repo} :: {remote}")
    path = hf_hub_download(repo_id=repo, filename=remote)
    shutil.copy2(path, dest)
    print(f"[ok] {dest} ({dest.stat().st_size // (1024**2)} MB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--z-image", action="store_true")
    ap.add_argument("--kontext", action="store_true")
    ap.add_argument("--flux-dev", action="store_true")
    ap.add_argument("--qwen-image", action="store_true")
    args = ap.parse_args()
    keys = []
    if args.z_image:
        keys.append("z_image")
    if args.kontext:
        keys.append("kontext")
    if args.flux_dev:
        keys.append("flux_dev")
    if args.qwen_image:
        keys.append("qwen_image")
    if not keys:
        keys = ["z_image", "kontext", "flux_dev", "qwen_image"]
    for key in keys:
        print(f"=== {key} ===")
        for item in ITEMS[key]:
            download_one(*item)
    print("Done.")


if __name__ == "__main__":
    main()
