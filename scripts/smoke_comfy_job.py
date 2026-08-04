"""
Track A smoke runner: submit a workflow API graph to headless ComfyUI and
record wall-clock + nvidia-smi peak VRAM.

Usage:
  # start ComfyUI first, e.g.:
  #   .venv\\Scripts\\python.exe engine\\comfyui\\main.py --listen 127.0.0.1 --port 8188 --lowvram
  .venv\\Scripts\\python.exe scripts\\smoke_comfy_job.py backend\\workflows\\wan22_ti2v_5b_t2i_api.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 30.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def nvidia_mem_mb() -> int | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
        return int(out.strip().splitlines()[0].strip())
    except Exception:
        return None


def wait_history(base: str, prompt_id: str, timeout_s: float) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hist = http_json("GET", f"{base}/history/{prompt_id}")
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(2.0)
    raise TimeoutError(f"prompt {prompt_id} not finished in {timeout_s}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow", type=Path, help="workflow JSON with top-level 'prompt' dict")
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    ap.add_argument("--timeout", type=float, default=3600.0)
    args = ap.parse_args()

    wf = json.loads(args.workflow.read_text(encoding="utf-8"))
    prompt = wf["prompt"] if "prompt" in wf else wf
    meta = wf.get("_meta", {})

    client_id = str(uuid.uuid4())
    mem0 = nvidia_mem_mb()
    t0 = time.time()
    print(f"[submit] {args.workflow.name} meta={meta.get('title')} mem0={mem0}MB")
    try:
        res = http_json(
            "POST",
            f"{args.base}/prompt",
            {"prompt": prompt, "client_id": client_id},
            timeout=120.0,
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[error] HTTP {e.code}: {body}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[error] submit failed: {e}", file=sys.stderr)
        return 2

    prompt_id = res.get("prompt_id")
    if not prompt_id:
        print(f"[error] unexpected response: {res}", file=sys.stderr)
        return 2
    print(f"[queued] prompt_id={prompt_id}")

    peak = mem0 or 0
    deadline = time.time() + args.timeout
    hist_entry = None
    while time.time() < deadline:
        m = nvidia_mem_mb()
        if m is not None and m > peak:
            peak = m
        try:
            hist = http_json("GET", f"{args.base}/history/{prompt_id}")
            if prompt_id in hist:
                hist_entry = hist[prompt_id]
                break
        except Exception:
            pass
        time.sleep(2.0)

    elapsed = time.time() - t0
    if hist_entry is None:
        print(f"[timeout] after {elapsed:.1f}s peak_vram={peak}MB")
        return 3

    status = hist_entry.get("status", {})
    outputs = hist_entry.get("outputs", {})
    ok = status.get("completed", False) or bool(outputs)
    print(
        json.dumps(
            {
                "workflow": str(args.workflow),
                "title": meta.get("title"),
                "tier": meta.get("tier"),
                "mode": meta.get("mode"),
                "prompt_id": prompt_id,
                "ok": ok,
                "wall_clock_s": round(elapsed, 1),
                "vram_start_mb": mem0,
                "vram_peak_mb": peak,
                "status": status,
                "output_keys": list(outputs.keys()),
            },
            indent=2,
        )
    )
    # Append one line to benchmarks results sidecar for Track A
    results = ROOT / "benchmarks" / "results.md"
    results.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"| {time.strftime('%Y-%m-%d %H:%M')} | {meta.get('tier','?')} | {meta.get('mode','?')} "
        f"| {args.workflow.name} | peak={peak}MB | {elapsed:.1f}s | ok={ok} |\n"
    )
    if not results.exists():
        results.write_text(
            "# Benchmark results (Track A)\n\n"
            "| when | tier | mode | workflow | vram | wall | ok |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with results.open("a", encoding="utf-8") as f:
        f.write(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
