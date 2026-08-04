"""
Track D benchmark harness for ImageGen (Wan2.2 on GTX 1650 Ti / 4GB).

Owned by Track D (Claude/Opus). Track A *runs* this; do not rewrite it here —
propose changes in plan.md §10 first.

What it does that the Track A smoke runner does not:
  * Launches ComfyUI itself with an explicit --flags set, so we can A/B
    --lowvram vs --novram vs --reserve-vram per model tier (Track D deliverable).
  * Samples GPU memory in a background thread at ~4 Hz (vs the smoke runner's
    2 s poll) for a truthful peak, and also records ComfyUI's own reported
    load/offload split via /system_stats.
  * Separates COLD (first run, includes weight load) from WARM (cached) timing
    by running the same graph N+1 times and dropping the first.
  * Patches width/height/length/steps/seed into the workflow graph so one JSON
    can be swept across resolutions/frame counts without editing the file.
  * Writes structured rows to benchmarks/bench_runs.jsonl (Track D's file).
    It never touches benchmarks/results.md (Track A's file).

Usage examples (ComfyUI NOT already running -- harness manages it):
  .venv\\Scripts\\python.exe benchmarks\\bench.py \\
      --workflow backend\\workflows\\wan22_ti2v_5b_t2i_api.json \\
      --flags "--lowvram" --repeat 2 --tier fast --mode t2i

  # A/B a flag set on the flagship, override resolution + steps:
  .venv\\Scripts\\python.exe benchmarks\\bench.py \\
      --workflow backend\\workflows\\wan22_t2v_a14b_t2v_api.json \\
      --flags "--novram" --width 384 --height 384 --length 13 --steps 10 \\
      --tier flagship --mode t2v --timeout 5400

  # Drive an already-running ComfyUI (skip launch), just measure:
  .venv\\Scripts\\python.exe benchmarks\\bench.py --workflow <wf> --no-launch

Notes:
  * Windows/Turing/CUDA 11.8: Triton is absent, so torch.compile is a no-go
    (verified 2026-08-03). Attention path is torch/SDPA mem-efficient. This
    harness does not attempt torch.compile; it exists to tune memory residency,
    which is the actual bottleneck on this card.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
COMFY_MAIN = ROOT / "engine" / "comfyui" / "main.py"
RUNS_FILE = ROOT / "benchmarks" / "bench_runs.jsonl"


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
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


def wait_server(base: str, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            http_json("GET", f"{base}/system_stats", timeout=5.0)
            return True
        except Exception:
            time.sleep(1.0)
    return False


def system_stats(base: str) -> dict | None:
    try:
        return http_json("GET", f"{base}/system_stats", timeout=5.0)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# VRAM sampler (background thread, ~4 Hz). Uses nvidia-smi so it captures the
# whole-process footprint incl. CUDA context + driver, matching Track A numbers.
# --------------------------------------------------------------------------- #
class VramSampler(threading.Thread):
    def __init__(self, period: float = 0.25):
        super().__init__(daemon=True)
        self.period = period
        # NB: do NOT name this `_stop` — that shadows threading.Thread._stop(),
        # which the interpreter calls internally on join()/is_alive(), raising
        # "'Event' object is not callable" after the thread finishes.
        self._stop_evt = threading.Event()
        self.samples: list[int] = []

    @staticmethod
    def _read_mb() -> int | None:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used",
                 "--format=csv,noheader,nounits"],
                text=True, timeout=10,
            )
            return int(out.strip().splitlines()[0].strip())
        except Exception:
            return None

    def run(self):
        while not self._stop_evt.is_set():
            m = self._read_mb()
            if m is not None:
                self.samples.append(m)
            self._stop_evt.wait(self.period)

    def stop(self):
        self._stop_evt.set()

    @property
    def peak(self) -> int | None:
        return max(self.samples) if self.samples else None

    @property
    def baseline(self) -> int | None:
        # first few samples ~= idle/driver footprint before weights load
        return min(self.samples[:8]) if self.samples else None


# --------------------------------------------------------------------------- #
# Workflow patching
# --------------------------------------------------------------------------- #
LATENT_NODES = (
    "EmptyHunyuanLatentVideo", "EmptyLatentImage", "EmptySD3LatentImage",
    "Wan22ImageToVideoLatent",  # fast-tier TI2V-5B T2V/I2V latent node
)


def patch_graph(prompt: dict, *, width, height, length, steps, seed, unet=None) -> dict:
    """Override common Wan2.2 graph params in-place-ish (returns a copy)."""
    g = json.loads(json.dumps(prompt))  # deep copy
    for node in g.values():
        ct = node.get("class_type", "")
        ins = node.get("inputs", {})
        if unet is not None and ct == "UnetLoaderGGUF" and "unet_name" in ins:
            ins["unet_name"] = unet
        if ct in LATENT_NODES:
            if width is not None and "width" in ins:
                ins["width"] = width
            if height is not None and "height" in ins:
                ins["height"] = height
            if length is not None and "length" in ins:
                ins["length"] = length
        if ct in ("KSampler", "KSamplerAdvanced"):
            if steps is not None and "steps" in ins:
                # KSamplerAdvanced split-expert graphs use start/end_at_step to
                # partition; rescale end proportionally so both experts keep
                # their share when total step count changes.
                old = ins["steps"]
                ins["steps"] = steps
                if "end_at_step" in ins and isinstance(ins["end_at_step"], int) and old:
                    frac = ins["end_at_step"] / old
                    ins["end_at_step"] = max(1, round(steps * frac))
                if "start_at_step" in ins and isinstance(ins["start_at_step"], int) and old:
                    frac = ins["start_at_step"] / old
                    ins["start_at_step"] = max(0, round(steps * frac))
            if seed is not None:
                if "seed" in ins:
                    ins["seed"] = seed
                if "noise_seed" in ins and ins.get("add_noise", "enable") != "disable":
                    ins["noise_seed"] = seed
    return g


# --------------------------------------------------------------------------- #
# One job submission + wait, with live VRAM peak capture
# --------------------------------------------------------------------------- #
def run_once(base: str, prompt: dict, timeout_s: float) -> dict:
    client_id = str(uuid.uuid4())
    t0 = time.time()
    res = http_json("POST", f"{base}/prompt",
                    {"prompt": prompt, "client_id": client_id}, timeout=120.0)
    prompt_id = res.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"no prompt_id in response: {res}")

    deadline = time.time() + timeout_s
    hist_entry = None
    while time.time() < deadline:
        try:
            hist = http_json("GET", f"{base}/history/{prompt_id}", timeout=15.0)
            if prompt_id in hist:
                hist_entry = hist[prompt_id]
                break
        except Exception:
            pass
        time.sleep(1.5)

    elapsed = time.time() - t0
    if hist_entry is None:
        return {"ok": False, "wall_s": round(elapsed, 1), "prompt_id": prompt_id,
                "reason": "timeout"}
    status = hist_entry.get("status", {})
    outputs = hist_entry.get("outputs", {})
    ok = status.get("completed", False) or bool(outputs)
    return {"ok": ok, "wall_s": round(elapsed, 1), "prompt_id": prompt_id,
            "output_keys": list(outputs.keys()), "status": status}


# --------------------------------------------------------------------------- #
# ComfyUI process management
# --------------------------------------------------------------------------- #
def launch_comfy(flags: list[str], port: int, log_path: Path) -> subprocess.Popen:
    cmd = [str(PY), str(COMFY_MAIN),
           "--listen", "127.0.0.1", "--port", str(port),
           "--disable-auto-launch", *flags]
    log = log_path.open("w", encoding="utf-8")
    print(f"[bench] launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    return proc


def main() -> int:
    ap = argparse.ArgumentParser(description="Track D Wan2.2 memory/perf bench harness")
    ap.add_argument("--workflow", type=Path, required=True)
    ap.add_argument("--flags", default="--lowvram",
                    help='ComfyUI launch flags to A/B, e.g. "--novram" or '
                         '"--lowvram --reserve-vram 0.5"')
    ap.add_argument("--no-launch", action="store_true",
                    help="assume ComfyUI already running on --base; just measure")
    ap.add_argument("--base", default=None, help="override base URL")
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--repeat", type=int, default=2,
                    help="total runs; first is COLD (weight load), rest WARM")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--length", type=int)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--unet", default=None,
                    help="override UnetLoaderGGUF unet_name (e.g. a different "
                         "quant .gguf) without editing the workflow")
    ap.add_argument("--tier", default="?")
    ap.add_argument("--mode", default="?")
    ap.add_argument("--label", default="", help="free-text tag for this A/B cell")
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--startup-timeout", type=float, default=180.0)
    args = ap.parse_args()

    base = args.base or f"http://127.0.0.1:{args.port}"
    flags = shlex.split(args.flags) if args.flags else []
    wf = json.loads(args.workflow.read_text(encoding="utf-8"))
    prompt_src = wf["prompt"] if "prompt" in wf else wf
    meta = wf.get("_meta", {})

    prompt = patch_graph(prompt_src, width=args.width, height=args.height,
                         length=args.length, steps=args.steps, seed=args.seed,
                         unet=args.unet)

    proc = None
    log_path = ROOT / "benchmarks" / f"comfy_bench_{args.port}.log"
    sampler = VramSampler(period=0.25)
    try:
        if not args.no_launch:
            proc = launch_comfy(flags, args.port, log_path)
            if not wait_server(base, args.startup_timeout):
                print(f"[bench] ComfyUI did not come up in {args.startup_timeout}s; "
                      f"see {log_path}", file=sys.stderr)
                return 2

        stats0 = system_stats(base)
        sampler.start()

        runs = []
        for i in range(max(1, args.repeat)):
            phase = "cold" if i == 0 else "warm"
            print(f"[bench] run {i + 1}/{args.repeat} ({phase}) ...")
            r = run_once(base, prompt, args.timeout)
            r["phase"] = phase
            steps_eff = args.steps or _infer_steps(prompt)
            if r.get("ok") and steps_eff:
                r["s_per_step"] = round(r["wall_s"] / steps_eff, 1)
            runs.append(r)
            print(f"[bench]   -> ok={r['ok']} wall={r['wall_s']}s "
                  f"s/step={r.get('s_per_step')}")

        sampler.stop()
        sampler.join(timeout=2.0)

        warm = [r for r in runs if r["phase"] == "warm" and r.get("ok")]
        warm_wall = min((r["wall_s"] for r in warm), default=None)

        row = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "workflow": args.workflow.name,
            "title": meta.get("title"),
            "tier": args.tier if args.tier != "?" else meta.get("tier", "?"),
            "mode": args.mode if args.mode != "?" else meta.get("mode", "?"),
            "flags": " ".join(flags),
            "label": args.label,
            "overrides": {"width": args.width, "height": args.height,
                          "length": args.length, "steps": args.steps,
                          "seed": args.seed, "unet": args.unet},
            "vram_baseline_mb": sampler.baseline,
            "vram_peak_mb": sampler.peak,
            "cold_wall_s": runs[0]["wall_s"] if runs else None,
            "warm_wall_s": warm_wall,
            "runs": runs,
            "system_stats_devices": (stats0 or {}).get("devices"),
        }
        RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with RUNS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

        print("\n[bench] === summary ===")
        print(json.dumps({k: row[k] for k in
                          ("tier", "mode", "flags", "label", "vram_baseline_mb",
                           "vram_peak_mb", "cold_wall_s", "warm_wall_s")}, indent=2))
        print(f"[bench] appended to {RUNS_FILE}")
        print("[bench] paste-ready markdown row for Track A results.md:")
        ov = row["overrides"]
        rescell = f"{ov['width'] or '-'}x{ov['height'] or '-'}/{ov['length'] or '-'}"
        print(f"| {row['ts'][:16]} | {row['tier']} | {row['mode']} | "
              f"{row['workflow']} | {row['flags']} | {rescell} | "
              f"peak={row['vram_peak_mb']}MB | cold={row['cold_wall_s']}s "
              f"warm={row['warm_wall_s']}s |")
        all_ok = all(r.get("ok") for r in runs)
        return 0 if all_ok else 1
    finally:
        if sampler.is_alive():
            sampler.stop()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except Exception:
                proc.kill()


def _infer_steps(prompt: dict) -> int | None:
    # For split-expert graphs, "total steps" is the KSampler `steps` value
    # (both experts share the same total; end_at_step partitions it).
    for node in prompt.values():
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced"):
            s = node.get("inputs", {}).get("steps")
            if isinstance(s, int):
                return s
    return None


if __name__ == "__main__":
    raise SystemExit(main())
