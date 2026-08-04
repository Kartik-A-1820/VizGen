"""Quick upscale smoke against running ComfyUI."""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "engine" / "comfyui" / "output" / "smoke_ti2v5b_t2i_00001_.png"
INP = ROOT / "engine" / "comfyui" / "input" / "smoke_apple.png"
WF = ROOT / "backend" / "workflows" / "upscale_realesrgan_x4_api.json"
BASE = "http://127.0.0.1:8188"


def main() -> int:
    if not SRC.exists():
        print(f"missing source image {SRC}")
        return 1
    INP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, INP)

    doc = json.loads(WF.read_text(encoding="utf-8"))
    prompt = doc["prompt"]
    prompt["1"]["inputs"]["image"] = "smoke_apple.png"

    body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(
        f"{BASE}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    pid = data["prompt_id"]
    print(f"queued {pid}")
    for _ in range(120):
        with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=30) as resp:
            hist = json.loads(resp.read().decode())
        if pid in hist:
            print(json.dumps(hist[pid].get("status", {}), indent=2))
            outs = hist[pid].get("outputs", {})
            print("outputs", outs)
            return 0 if hist[pid].get("status", {}).get("completed") else 1
        time.sleep(1)
    print("timeout")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
