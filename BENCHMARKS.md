# VizGen Benchmarks

Hardware: **NVIDIA GTX 1650 Ti (4 GB VRAM, Turing), 16 GB RAM, Windows 11, CUDA 11.8**, ComfyUI `--lowvram`, GGUF models.

All models run GGUF-quantized with one model resident at a time (load-use-release). These numbers characterize what "SOTA image generation on a 4 GB card" actually looks like.

---

## TL;DR

- **Best overall on 4 GB: Z-Image Turbo.** Fastest *and* the highest quality actually verified by inspecting outputs — near-SOTA photorealism with accurate prompt adherence. It's a few-step ("turbo") model, so ~**3–3.5 min** at 512–768² (≈**80 s** once the encoder is warm).
- **768² is the sweet spot.** 1024² pushes VRAM to 94 % and collapses into weight-streaming (~7 min).
- **FLUX.1-dev / Qwen-Image** run without OOM but were only smoke-tested at 4 steps (a "does it run" check, not representative quality) — keep as quality options pending a proper multi-step visual comparison.
- **Editing (FLUX.1 Kontext)** works but is a **slow tier** (~15–40 min/edit) — the 12 B model exceeds 4 GB and thrashes.

---

## Generation — Z-Image Turbo (measured + outputs visually verified)

8 steps, cfg 1.0, euler/simple. VRAM peak via nvidia-smi. First run is cold (includes a ~5 min one-time load of the 5.3 GB Qwen3 text encoder on CPU); sampling itself is only ~80 s.

| Resolution | VRAM peak | Wall time | Verdict |
|---|---|---|---|
| 512² | 2129 MB | ~188 s (~3.1 min) | fast, comfortable |
| **768²** | 2785 MB | **~202 s (~3.4 min)** | ⭐ **recommended** — best quality that still fits |
| 1024² | 3785 MB (94 %) | ~424 s (~7 min) | thrashes (52 s/step) — avoid on 4 GB |

**Quant note:** Q3_K_S ≈ Q4_K_M on VRAM peak (2127 vs 2129 @512²; identical @768²/1024²) because peak is **activation-bound, not weight-bound** — the smaller quant buys no headroom. **Use Q4_K_M** (slightly sharper).

## Generation — FLUX.1-dev & Qwen-Image (smoke only — timing, not quality)

Ran without OOM at **4 steps** (a run-check, not a quality run; FLUX.1-dev normally needs ~20–28 steps). Output images were **not** visually verified.

| Model | Test | VRAM peak | Wall time |
|---|---|---|---|
| FLUX.1-dev (Q4_K_S) | 512², 4 steps | 2995 MB | ~561 s (~9.4 min) |
| Qwen-Image Lightning (Q4_K_M) | 512², 4 steps | 2793 MB | ~928 s (~15.5 min) |

## Editing — FLUX.1 Kontext (measured)

20-step instruction edit. The graph is correct and it genuinely edits, but Kontext is a 12 B model (~5 GB even at Q3_K_S) — larger than 4 GB VRAM — so **0 MB stays resident** and every step streams the full model.

| Config | Per-step | Total |
|---|---|---|
| Q3_K_S, 20 steps, 512² | ~116 s/step | **~40 min/edit** (~23 min @12 steps, ~15 min @8) |

→ Editing is functional but a **slow tier**; the UI should surface an honest ETA.

## End-to-end (full staged pipeline, measured)

One `POST /api/jobs` with **enhance + upscale** on: Qwen prompt-rewrite + auto-negative → Z-Image 768² → RealESRGAN ×4 → **3072² output**. Load-use-release between every stage. **~10 min total** (CPU text-encode dominates; sampling + upscale are fast). Result quality: near-SOTA photoreal, accurate to prompt.

---

## Cross-cutting findings

1. **Resolution matters more than quantization.** 768² is the practical ceiling on 4 GB; 1024² collapses into per-step weight-streaming.
2. **VRAM peak is activation-bound**, so a smaller GGUF quant does *not* free headroom — pick quant for quality, manage memory via resolution.
3. **The CPU text-encode is the dominant cold-start cost**, not GPU sampling. The biggest remaining optimization is caching/reusing text embeddings.
4. **torch.compile / Triton is a no-go** on this Windows/Turing box; attention runs on torch SDPA.
5. **Any model larger than ~4 GB (FLUX-class 12 B) thrashes** — it can't stay resident, so it streams every step. Few-step "turbo/Lightning" models are the right fit for this GPU.

## Reproduce

```bat
:: Z-Image resolution/quant matrix
.venv\Scripts\python.exe benchmarks\zimage_bench.py

:: generic single-workflow harness (VRAM peak + cold/warm timing)
.venv\Scripts\python.exe benchmarks\bench.py --workflow backend\workflows\<wf>.json --no-launch --base http://127.0.0.1:8188
```

Raw data: `benchmarks/zimage_benchmark.md`, `benchmarks/results.md`, `benchmarks/generate_model_smoke.md`.
