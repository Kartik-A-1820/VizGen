"""
Track A — auxiliary models (not Wan gen lineup):
  - RealESRGAN x4 for super-resolution
  - Small instruct LLM for prompt enhancement (CPU-friendly)

Usage:
  .venv\\Scripts\\python.exe scripts\\download_aux_models.py
  .venv\\Scripts\\python.exe scripts\\download_aux_models.py --upscale-only
  .venv\\Scripts\\python.exe scripts\\download_aux_models.py --llm-only
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"


def download_file(repo: str, remote: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"[skip] {dest.name} ({dest.stat().st_size // (1024**2)} MB)")
        return
    print(f"[dl] {repo} :: {remote}")
    path = hf_hub_download(repo_id=repo, filename=remote)
    shutil.copy2(path, dest)
    print(f"[ok] {dest} ({dest.stat().st_size // (1024**2)} MB)")


def download_upscale() -> None:
    # Classic RealESRGAN x4plus — ComfyUI UpscaleModelLoader
    download_file(
        "fofr/comfyui",
        "upscale_models/RealESRGAN_x4plus.pth",
        MODELS / "upscale_models" / "RealESRGAN_x4plus.pth",
    )


def download_llm() -> None:
    """
    Qwen2.5-1.5B-Instruct — small, strong at instruction following,
    intended for CPU inference so GPU stays free for Wan.
    """
    dest = MODELS / "llm" / "Qwen2.5-1.5B-Instruct"
    if dest.exists() and any(dest.rglob("*.safetensors")):
        print(f"[skip] LLM already present at {dest}")
        return
    print(f"[dl] Qwen/Qwen2.5-1.5B-Instruct -> {dest}")
    snapshot_download(
        repo_id="Qwen/Qwen2.5-1.5B-Instruct",
        local_dir=str(dest),
        ignore_patterns=["*.md", "*.txt", "LICENSE*", ".gitattributes"],
    )
    print(f"[ok] {dest}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upscale-only", action="store_true")
    ap.add_argument("--llm-only", action="store_true")
    args = ap.parse_args()
    do_all = not args.upscale_only and not args.llm_only
    if do_all or args.upscale_only:
        download_upscale()
    if do_all or args.llm_only:
        download_llm()
    print("Done.")


if __name__ == "__main__":
    main()
