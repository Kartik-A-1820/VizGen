"""
Standalone RealESRGAN x4 (same weights as ComfyUI upscale_models).

Uses spandrel (already a ComfyUI dependency). Defaults to CUDA if free VRAM
looks available, else CPU.

Usage:
  .venv\\Scripts\\python.exe scripts\\upscale_image.py engine\\comfyui\\output\\smoke_ti2v5b_t2i_00001_.png
  .venv\\Scripts\\python.exe scripts\\upscale_image.py in.png -o out_x4.png --device cpu
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models" / "upscale_models" / "RealESRGAN_x4plus.pth"


def pick_device(requested: str) -> torch.device:
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            print("[warn] CUDA unavailable, using CPU", file=sys.stderr)
            return torch.device("cpu")
        return torch.device("cuda")
    # auto
    if torch.cuda.is_available():
        try:
            free, total = torch.cuda.mem_get_info()
            # need headroom for tiles; ~1GB free is enough for tiled x4 of 512
            if free > 900 * 1024 * 1024:
                return torch.device("cuda")
        except Exception:
            return torch.device("cuda")
    return torch.device("cpu")


@torch.inference_mode()
def upscale(path_in: Path, path_out: Path, model_path: Path, device: torch.device) -> None:
    from spandrel import ModelLoader

    if not model_path.exists():
        raise SystemExit(
            f"Missing {model_path}. Run: python scripts/download_aux_models.py --upscale-only"
        )

    img = Image.open(path_in).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    # NCHW
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device)

    print(f"[load] {model_path.name} on {device}", file=sys.stderr)
    descriptor = ModelLoader().load_from_file(str(model_path))
    model = descriptor.model.to(device).eval()

    # tiled inference for low VRAM
    tile = 256 if device.type == "cuda" else 512
    overlap = 16
    _, _, h, w = t.shape
    scale = int(getattr(descriptor, "scale", 4) or 4)
    out_h, out_w = h * scale, w * scale
    out = torch.zeros(1, 3, out_h, out_w, device=device, dtype=t.dtype)

    def run_tile(x: torch.Tensor) -> torch.Tensor:
        y = model(x)
        return y

    ys = list(range(0, h, tile - overlap))
    xs = list(range(0, w, tile - overlap))
    for y0 in ys:
        for x0 in xs:
            y1 = min(y0 + tile, h)
            x1 = min(x0 + tile, w)
            y0c = max(0, y1 - tile)
            x0c = max(0, x1 - tile)
            patch = t[:, :, y0c:y1, x0c:x1]
            up = run_tile(patch)
            # write corresponding region
            oy0, ox0 = y0c * scale, x0c * scale
            oy1, ox1 = y1 * scale, x1 * scale
            # simple overwrite (overlap seams acceptable for smoke)
            out[:, :, oy0:oy1, ox0:ox1] = up[:, :, : oy1 - oy0, : ox1 - ox0]

    out = out.clamp(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy()
    out_u8 = (out * 255.0).round().astype(np.uint8)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out_u8).save(path_out)
    print(f"[ok] {path_in.name} {img.size} -> {path_out} {Image.open(path_out).size}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    args = ap.parse_args()
    out = args.output or args.input.with_name(args.input.stem + "_x4.png")
    device = pick_device(args.device)
    upscale(args.input, out, args.model, device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
