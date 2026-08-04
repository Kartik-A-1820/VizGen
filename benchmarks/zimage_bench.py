"""Track D — benchmark all available text-to-image generators across resolutions.

Currently that's Z-Image Turbo (Q4_K_M vs Q3_K_S). Adult subject (model quality
+ speed comparison; subject is incidental to the benchmark). Records VRAM peak
(nvidia-smi, 4Hz) + wall time per (model, resolution) to zimage_benchmark.md.

Encoder (qwen_3_4b, 5.3GB) stays warm across runs (no /free between), so the
first run is COLD (includes encoder load) and the rest are WARM — both reported.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8188"
WF = ROOT / "backend" / "workflows" / "z_image_turbo_t2i_api.json"
OUT = ROOT / "benchmarks" / "zimage_benchmark.md"

PROMPT = ("a realistic full-body fashion photograph of a woman in her mid-20s wearing a "
          "casual tank top and denim shorts, standing outdoors in a sunny park, natural "
          "daylight, photorealistic, sharp focus, highly detailed, professional photography")
NEG = "blurry, low quality, deformed, extra limbs, fused, watermark, text, distorted"

STEPS, CFG, SEED = 8, 1.0, 42
MATRIX = [
    ("z_image_turbo-Q4_K_M.gguf", 512, 512),
    ("z_image_turbo-Q4_K_M.gguf", 768, 768),
    ("z_image_turbo-Q4_K_M.gguf", 1024, 1024),
    ("z_image_turbo-Q3_K_S.gguf", 512, 512),
    ("z_image_turbo-Q3_K_S.gguf", 768, 768),
    ("z_image_turbo-Q3_K_S.gguf", 1024, 1024),
]


def http(method, path, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=10)
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_evt = threading.Event()
        self.peak = 0

    def run(self):
        while not self.stop_evt.is_set():
            self.peak = max(self.peak, vram())
            self.stop_evt.wait(0.25)


def fill(unet, w, h):
    wf = json.loads(WF.read_text())["prompt"]
    tok = {"${prompt}": PROMPT, "${negative_prompt}": NEG, "${width}": w, "${height}": h,
           "${seed}": SEED, "${steps}": STEPS, "${cfg}": CFG,
           "${sampler}": "euler", "${scheduler}": "simple"}

    def sub(v):
        if isinstance(v, str):
            return tok.get(v, v)
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        if isinstance(v, list):
            return [sub(x) for x in v]
        return v
    g = sub(wf)
    for node in g.values():
        if node.get("class_type") == "UnetLoaderGGUF":
            node["inputs"]["unet_name"] = unet
    return g


def run_one(unet, w, h):
    prompt = fill(unet, w, h)
    s = Sampler(); s.start()
    t0 = time.time()
    pid = str(http("POST", "/prompt", {"prompt": prompt, "client_id": str(uuid.uuid4())})["prompt_id"])
    ok, fname = False, ""
    while time.time() - t0 < 1800:
        try:
            hist = http("GET", f"/history/{pid}")
            if pid in hist:
                outs = hist[pid].get("outputs", {})
                files = [i["filename"] for v in outs.values() for i in v.get("images", [])]
                ok, fname = bool(files), (files[0] if files else "")
                break
        except Exception:
            pass
        time.sleep(2)
    dt = time.time() - t0
    s.stop_evt.set(); s.join(timeout=2)
    return {"unet": unet, "w": w, "h": h, "ok": ok, "wall_s": round(dt, 1),
            "vram_peak_mb": s.peak, "file": fname}


def main():
    rows = []
    for i, (unet, w, h) in enumerate(MATRIX):
        phase = "cold" if i == 0 else "warm"
        print(f"[{i+1}/{len(MATRIX)}] {unet} {w}x{h} ({phase}) ...", flush=True)
        r = run_one(unet, w, h)
        r["phase"] = phase
        rows.append(r)
        print(f"    ok={r['ok']} wall={r['wall_s']}s peak={r['vram_peak_mb']}MB file={r['file']}", flush=True)

    lines = ["# Z-Image Turbo benchmark (Track D)", "",
             f"Prompt: _{PROMPT}_", "",
             f"Settings: {STEPS} steps, cfg {CFG}, euler/simple, seed {SEED}. "
             "Encoder warm across runs (first = cold incl. 5.3GB qwen3 load).", "",
             "| model | resolution | phase | VRAM peak | wall time | ok | output |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        q = "Q4_K_M" if "Q4" in r["unet"] else "Q3_K_S"
        lines.append(f"| Z-Image {q} | {r['w']}x{r['h']} | {r['phase']} | "
                     f"{r['vram_peak_mb']} MB | {r['wall_s']} s | {r['ok']} | {r['file']} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
