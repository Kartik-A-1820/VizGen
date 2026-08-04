"""Smoke Z-Image Turbo T2I via ComfyUI API."""
from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "backend" / "workflows" / "z_image_turbo_t2i_api.json"
BASE = "http://127.0.0.1:8188"


def replace_tokens(obj, tokens):
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            return tokens.get(obj[2:-1], obj)
        return obj
    if isinstance(obj, list):
        return [replace_tokens(x, tokens) for x in obj]
    if isinstance(obj, dict):
        return {k: replace_tokens(v, tokens) for k, v in obj.items()}
    return obj


def main() -> int:
    doc = json.loads(WF.read_text(encoding="utf-8"))
    tokens = {
        "prompt": "a red apple on a wooden table, soft natural light, photorealistic",
        "negative_prompt": "blurry, low quality, watermark",
        "width": 512,
        "height": 512,
        "seed": 42,
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
    }
    prompt = replace_tokens(doc["prompt"], tokens)
    body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(
        f"{BASE}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data or "node_errors" in data and data.get("node_errors"):
        print(json.dumps(data, indent=2)[:2000])
        return 2
    pid = data["prompt_id"]
    print(f"queued {pid}")
    t0 = time.time()
    for _ in range(3600):
        with urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=30) as resp:
            hist = json.loads(resp.read().decode())
        if pid in hist:
            st = hist[pid].get("status", {})
            print(json.dumps({"status": st.get("status_str"), "completed": st.get("completed"), "wall_s": round(time.time() - t0, 1)}, indent=2))
            if st.get("status_str") == "error":
                msgs = st.get("messages", [])
                for m in msgs:
                    if m and m[0] == "execution_error":
                        print(m[1].get("exception_message", "")[:500])
                return 1
            return 0 if st.get("completed") else 1
        time.sleep(2)
    print("timeout")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
