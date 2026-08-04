from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "benchmarks" / "generate_model_smoke.md"

from backend.app.comfy_client import ComfyUIClient
from backend.app.registry import get_model

PROMPT = "a crisp product photo of a red ceramic mug on a wooden desk, soft daylight, sharp focus"
NEGATIVE = "blurry, low quality, distorted, watermark, text"


def vram_used() -> int:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


class VramSampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_evt = threading.Event()
        self.peak_mb = 0

    def run(self) -> None:
        while not self.stop_evt.is_set():
            self.peak_mb = max(self.peak_mb, vram_used())
            self.stop_evt.wait(0.5)


async def run_one(model_id: str, width: int, height: int, steps: int) -> dict:
    model = get_model(model_id)
    client = ComfyUIClient()
    await client.free()
    job = {
        "id": str(uuid.uuid4()),
        "model_id": model.id,
        "mode": "generate",
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE,
        "params": {
            **model.defaults,
            "width": width,
            "height": height,
            "steps": steps,
            "seed": 42,
        },
    }
    sampler = VramSampler()
    sampler.start()
    t0 = time.time()
    outputs: list[str] = []
    ok = False
    error = ""
    try:
        outputs = await client.run_workflow(model, job)
        ok = bool(outputs)
    except Exception as exc:
        error = str(exc)
    finally:
        elapsed = round(time.time() - t0, 1)
        sampler.stop_evt.set()
        sampler.join(timeout=2)
        await client.free()
    return {
        "model_id": model_id,
        "workflow": model.workflow,
        "resolution": f"{width}x{height}",
        "steps": steps,
        "ok": ok,
        "wall_s": elapsed,
        "vram_peak_mb": sampler.peak_mb,
        "output": outputs[0] if outputs else "",
        "error": error.replace("\n", " ")[:300],
    }


def write_results(rows: list[dict]) -> None:
    lines = [
        "# Generate Model Smoke",
        "",
        f"Prompt: _{PROMPT}_",
        "",
        "| model | workflow | resolution | steps | VRAM peak | wall time | ok | output/error |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        result = row["output"] or row["error"]
        lines.append(
            f"| {row['model_id']} | {row['workflow']} | {row['resolution']} | {row['steps']} | "
            f"{row['vram_peak_mb']} MB | {row['wall_s']} s | {row['ok']} | {result} |"
        )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", default=["qwen-image-lightning", "flux-dev-q4"])
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    args = parser.parse_args()

    rows = []
    for model_id in args.models:
        print(f"[smoke] {model_id} {args.width}x{args.height} steps={args.steps}", flush=True)
        row = await run_one(model_id, args.width, args.height, args.steps)
        print(row, flush=True)
        rows.append(row)
        write_results(rows)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
