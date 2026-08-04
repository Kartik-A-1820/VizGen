# Track D — Performance / Quantization / Offload Tuning Notes

Owner: Claude (Opus 4.8). This is Track D's artifact. It does **not** edit
`results.md` (Track A) or `models_registry.yaml` (Track B) — the "Proposals for
Track B" section at the bottom is what Track B merges.

Environment verified this session (2026-08-03):
`torch 2.7.1+cu118`, GPU cap `(7,5)` sm_75 Turing, total VRAM **4.29 GB** (4096 MB usable).
Installed: torch/SDPA only. **Absent**: `triton`, `xformers`, `bitsandbytes`, `sageattention`.

---

## 1. torch.compile / Triton — GO/NO-GO: **NO-GO** (verified, not guessed)

- `torch.compile(mode="reduce-overhead")` on a trivial CUDA module raises
  `TritonMissing: Cannot find a working triton installation`. Confirmed live.
- Triton has no working install here and the Windows Triton story on Turing is
  the shakiest link in the stack (plan §9). Even the community `triton-windows`
  fork would be a speed play, and **speed is not the flagship bottleneck** — see
  §2: the flagship is memory-bandwidth-bound on CPU→GPU weight streaming, which
  `torch.compile` (a compute-graph optimizer) cannot address. The GPU is idle
  waiting for weights, not waiting on kernels.
- **Decision**: do not pursue torch.compile for either tier. Attention path
  stays torch **SDPA mem-efficient** (`--use-pytorch-cross-attention`, already
  ComfyUI's default here — confirmed `mem_efficient_sdp_enabled() == True`).
  `--use-split-cross-attention` is the fallback if any graph OOMs in attention.

## 2. Flagship A14B on 4GB — the hard physical wall

Track A's thrash log (flagship T2V):
`747.57 MB usable, 0.00 MB loaded, 5186.41 MB offloaded, 1107.36 MB buffer reserved` → ~226 s/step → **~54 min / 17 frames**.

Root cause is not tunable-away: **one A14B Q2_K expert on disk is 5054 MB, which
exceeds total VRAM (4096 MB).** You cannot make a 5 GB weight set resident in a
4 GB card. `0.00 MB loaded` is therefore not a misconfiguration — it is forced.
Every diffusion step re-streams the full expert from system RAM per-layer, and
Q2_K is already the **smallest** A14B quant on disk (no Q1 exists). So:

- No `--lowvram`/`--novram`/`--reserve-vram` value can hold an expert resident.
  Offload flags only shuffle *which* 4 GB is reserved vs streamed; they can't
  fit 5 GB into 4 GB.
- **Why T2I "works" at 14 min but T2V is 54 min**: for a single frame the
  activation tensors are tiny, so the streamed-weight overhead is paid over few,
  cheap steps → 3280 MB peak, tolerable. For 17 frames the activations balloon
  and contend with the streaming buffer → the ~226 s/step catastrophe.

**Recommendation (engineering reality, not a model-family change — stays within
Wan2.2, so §4 Rule 3 is untouched):**
- Treat **A14B as a stills-only "max-quality, ~14 min" tier.** Its 4 GB video
  path is physically thrash-bound and not worth deep tuning time.
- **Flagship-quality *video* on this card = the TI2V-5B tier**, which actually
  fits (§3). This is a capability limit of the 4 GB card, not of Wan2.2.
- Levers that *do* help A14B stills marginally (bench.py A/B candidates, low
  priority): fewer steps (each step = one full 5 GB stream, so 12→8 steps ≈ −33%
  wall), `--disable-smart-memory` + `--cache-none` to stop ComfyUI retaining
  dual-expert bookkeeping, and `--cpu-vae` to keep the VAE off-GPU during decode.
- **Workflow idea for Track A** (their file, their call — proposing only):
  the current graph loads *both* experts as live nodes up front. Splitting into
  two sequential runs (high-noise → save latent → low-noise) guarantees only one
  expert's memory manager is ever active. May cut peak/thrash. Needs their sign-off.
- Q4_K_M A14B (9203 MB/expert) is on disk but **should not be smoke-timed for
  video** — at >2× the Q2_K size it will thrash strictly harder; only meaningful
  for stills if a quality A/B vs Q2_K justifies the extra minutes. Deprioritized.

## 3. Fast tier TI2V-5B — the real tuning surface

Track A: T2I 2857 MB, **T2V 3856 MB (94% of 4 GB)**. The video path is one config
bump from OOM. This is where tuning actually pays off. On-disk quants:
Q3_K_M 2430 MB / Q4_K_M 3274 MB / Q5_K_M 3634 MB.

bench.py A/B plan (queued — each run is ~10–13 min, so this is a benchmarking
session, not a live-chat task):
1. **Split the video default to Q3_K_M.** Q3 (2430 MB) vs Q4 (3274 MB) buys
   ~840 MB headroom → removes the 94%-of-VRAM cliff and likely enables either
   more frames or 512² video. Keep **Q4_K_M as the stills default** (2857 MB has
   room, quality matters more on a single frame). A/B Q3 vs Q4 T2V quality on a
   fixed seed to confirm the quant drop is acceptable.
2. `--reserve-vram 0.4` on the fast tier: give ComfyUI a predictable safety
   buffer to cut fragmentation-OOM risk near the ceiling. A/B peak + wall vs bare
   `--lowvram`.
3. **ToMe** (ComfyUI `TomePatchModel` node, ratio 0.3–0.5) on 5B T2V: token
   merging cuts attention tokens → both speed and peak-memory win, quality cost
   to be A/B'd. This is the "opt-in speed toggle" deliverable. Insert as a model
   patch before sampling; expose as a per-job toggle later.
4. Confirm `--lowvram` (partial residency, Track A saw `1709 loaded / 1647
   offloaded` on 5B T2I — healthy, not thrash) beats `--novram` (forces full
   offload → needless streaming) for this tier. Expectation: keep `--lowvram`.

## 4. bench.py harness — DELIVERED

`benchmarks/bench.py` (Track D-owned). Over the Track A smoke runner it adds:
launches ComfyUI itself with an explicit `--flags` set (for flag A/B), 4 Hz VRAM
sampling for a truthful peak, cold-vs-warm separation via `--repeat`, and
width/height/length/steps/seed graph patching (with correct split-expert
`start/end_at_step` rescaling — verified: 12 steps split 6/6 → 10 steps split
5/5). Writes structured rows to `bench_runs.jsonl` (Track D's file) and prints a
paste-ready markdown row for Track A's `results.md`. Runs stay in Track A/D's
lane; nothing here writes another track's files.

Example A/B invocation:
```
.venv\Scripts\python.exe benchmarks\bench.py ^
  --workflow backend\workflows\wan22_ti2v_5b_t2v_api.json ^
  --flags "--lowvram --reserve-vram 0.4" --repeat 2 --tier fast --mode t2v ^
  --label "q4_reserve0.4"
```

---

## 5. Proposals for Track B → `models_registry.yaml` (merge these)

Grounded in verified env + Track A numbers + §2's physical constraint. Live A/B
(§3) may tighten the fast-tier video quant, but these flag sets are safe now:

```yaml
# Track D flag/quant recommendations — 2026-08-03
# Fast tier: keep Q4_K_M for stills, split video default to Q3_K_M for headroom.
wan22-ti2v-5b:
  comfy_launch_flags: ["--lowvram", "--reserve-vram", "0.4", "--use-pytorch-cross-attention"]
  # optional per-mode quant override once §3.1 A/B confirms Q3 video quality:
  #   t2i -> Wan2.2-TI2V-5B-Q4_K_M.gguf   (2857 MB peak, room to spare)
  #   t2v -> Wan2.2-TI2V-5B-Q3_K_M.gguf   (~840 MB headroom vs Q4, kills the 94% cliff)
  tome_ratio: 0.0        # opt-in; 0.3-0.5 for a speed/memory toggle, A/B pending

# Flagship A14B: physically stills-practical only on 4GB (single Q2_K expert 5054MB > 4096MB VRAM).
# Do NOT advertise a fast video path here; UI should label video "very slow / experimental".
wan22-t2v-a14b-q2k:
  comfy_launch_flags: ["--lowvram", "--disable-smart-memory", "--cache-none", "--cpu-vae"]
  ui_note: "Max-quality stills ~14 min. Video is thrash-bound (~54 min/17f) — use TI2V-5B for practical video."

# torch.compile: NO-GO on this box (Triton absent, Windows/Turing). Do not add a compile flag.
```

**Net registry guidance for the dropdown (§4 Rule 4):** two enforced entries stay
as-is (TI2V-5B fast, A14B-Q2_K flagship). No third mid-tier variant is justified
by Track D data — Q3_K_M is a *per-mode quant swap inside the fast entry*, not a
new dropdown model. That keeps the enforced lineup intact; no §4 change proposed.
