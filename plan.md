# VizGen — Local SOTA Image Generation & Editing Server

Owner: kartik | Machine: Windows 11, GTX 1650 Ti (4GB VRAM, Turing sm_75, no HW FP8), 16GB RAM, CUDA 11.8, torch 2.7.1+cu118.
Repo target: https://github.com/Kartik-A-1820/VizGen.git

> **2026-08-04 — MAJOR PIVOT (by kartik).** Project is now **image-only**. Video generation (Wan2.2 t2v/i2v) is **removed** — it was beyond the 4GB card's practical reach. New goal: **near-SOTA local image generation + text-instruction image editing**, with a multi-model dropdown and a staged enhance/generate/edit/upscale pipeline. This document is the source of truth; any agent can continue from §7 (Current Status & Remaining Work).

## 0. Governance — read before touching anything

- **This plan is locked except by kartik.** §4 (Model Strategy) and the track boundaries in §7 are enforced. No agent may change the model lineup, reassign a track, or edit another track's files on their own initiative — write a proposal in §10 and wait for kartik.
- **Each track owns fixed files/dirs** (per §7). Don't edit outside your lane; if blocked, note it in §10 and keep going in your own lane.
- **Status fields are mandatory upkeep** — update §7 checkboxes in the same session you make progress.
- Agents: **Claude (Opus 4.8)**, **Codex (GPT-5.5 medium)**, **Grok 4.5 High**, **AGY (Sonnet 4.6 thinking)**.

## 1. Goal

A **fast, local, self-hosted image server** — open weights, no cloud, no external moderation layer — that gets **as close to ChatGPT-image / Nano-Banana quality as a 4GB GPU allows**, with these first-class features:
- **Generate** (text → image) with a **multi-model dropdown** (several SOTA models, user-selectable).
- **Edit** (image + natural-language instruction → edited image) — the "say what to change" capability, via FLUX.1 Kontext.
- **Prompt enhancer** (local LLM rewrites prompt + auto-fills negative).
- **Upscale** (×4 super-resolution).
- **Staged pipeline** that loads each model only when needed and releases it right after (mandatory on 4GB — see §3/§5).
- **Live UI progress** (stage + ETA) and a gallery.

**Honest ceiling (state this to the user, don't oversell):** literal ChatGPT/Nano-Banana parity is not achievable on 4GB (those are far larger, datacenter-served). We target **near-SOTA open-weight quality** and the **same class of instruction editing**, at minutes-per-image on heavy models (seconds-to-a-minute on few-step "turbo" models).

## 2. Hardware Reality

GTX 1650 Ti: 4GB VRAM, Turing, no FP8 tensor cores, ~192GB/s bandwidth. 16GB system RAM (the tighter constraint in practice — see §5). Binding rules:
- Everything runs **GGUF-quantized (Q4/Q5) + `--lowvram` weight streaming**; only one model resident at a time.
- **Few-step models win big** (turbo/Lightning) — fewer sampling steps ≈ far less wall-clock, and the umT5/T5 text-encode on CPU is the real latency sink (~minutes) on this 16GB box.
- **Triton/torch.compile = NO-GO** on this Windows/Turing box (verified: `TritonMissing`). Attention = torch SDPA. Don't chase compile.

## 3. Architecture (already built — reuse)

```
Web UI (React/Vite, :5173)
      │  REST + WebSocket (stage, progress, ETA)
FastAPI backend (:8000) ── SQLite job queue ── staged worker
      │   stages: [enhance?] → [generate | edit] → [upscale?]
      │   ComfyUI /free between EVERY stage (load-use-release)
ComfyUI engine (:8188, --lowvram) ── GGUF image/edit models · encoders · RealESRGAN
Qwen2.5-1.5B (CPU subprocess) ── prompt + negative enhancer
```

- **ComfyUI** is the engine (best low-VRAM manager, GGUF loader, no safety-checker). Driven headlessly over its HTTP/WS API.
- **FastAPI** owns the job queue, the staged pipeline, the model registry (the dropdown), and progress/ETA.
- The **staged worker + `/free` load-release mechanism + enhancer + upscaler + ETA/stage UI already exist and work** (built 2026-08-04). The pivot mostly swaps the **generation/edit models**, not the architecture.

## 4. Model Strategy — ENFORCED (changeable only by kartik)

**Rule 1 — Image only.** No video. Wan2.2 and all t2v/i2v code/weights are removed.

**Rule 2 — Multi-model dropdown for generation.** Offer several selectable SOTA image models; the UI dropdown is driven entirely by `backend/models_registry.yaml`. Candidate lineup (validate feasibility on 4GB per §7 Track A; add in priority order):
- **Z-Image Turbo (6B)** — *primary/default*: newest low-VRAM SOTA (Nov 2025), few-step turbo = fastest on 4GB, best fit. GGUF.
- **Qwen-Image (GGUF + Lightning LoRA)** — strong quality, 4–8 step. Same family as the edit model below → cohesive stack.
- **FLUX.1-dev (GGUF Q4)** — highest prompt adherence/quality, slowest, tightest on 4GB. Include as the "max quality, slow" option.

**Rule 3 — Editing = FLUX.1 Kontext [dev]** (kartik's choice). Text-instruction editing: object/style/background swap, text edits. GGUF-quantized. Needs: Kontext GGUF UNet, `t5xxl` + `clip_l` encoders, Flux `ae.safetensors` VAE.

**Rule 4 — Features, model chosen internally by task.** The backend routes each request to the right model automatically:
- task = **generate** → selected generation model.
- task = **edit** → FLUX.1 Kontext (regardless of dropdown gen model).
- feature **enhance** → Qwen2.5-1.5B (CPU). feature **upscale** → RealESRGAN ×4.
"Sometimes editing only" → an edit request just runs the edit (+ optional enhance/upscale) stages; no generation.

**Rule 5 — All models GGUF + load-release.** Only one resident at a time; `/free` between stages (§5). No model family enters the default lineup without Track A feasibility evidence in `benchmarks/results.md`; gaps → §10 for kartik.

### 4.1 Aux models (kept from before)
- **Qwen2.5-1.5B-Instruct** (`models/llm/`) — prompt + negative enhancer (CPU). ✅ present & working.
- **RealESRGAN_x4plus** (`models/upscale_models/`) — ×4 upscaler. ✅ present.

### 4.2 Removed — PERMANENT (kartik's firm decision 2026-08-04: "never returning to video")
Video is **completely out of scope forever**. This is not a deprecation — **strip it entirely**, no compatibility stubs, no video vocabulary anywhere in the code:
- **Weights**: Wan2.2 TI2V-5B / T2V-A14B (all quants), umT5 encoder, Wan VAEs — **deleted from disk** (✅ done by Track D 2026-08-04; frees ~45GB). Do not re-download.
- **Backend code**: NO `t2v`/`i2v`/`video` mode names, NO 410 "video removed" stub, NO VHS/VideoCombine/`frames`/`fps` handling, NO umT5 references. `JobCreate.mode` = `generate | edit` only. Remove the concept, don't gate it.
- **Workflows/registry/UI**: no video graphs, registry entries, or UI modes. Downloaders fetch image/edit weights only.
- **Stale comments** mentioning umT5/video/Wan should be cleaned as encountered.

## 5. Memory / Load-Release Policy (the core 4GB discipline)

Applies to every job; already implemented in `backend/app/worker.py` + `comfy_client.py`:
1. Stages run **sequentially**, each loads its model, runs, then the worker calls ComfyUI **`POST /free {unload_models,free_memory}`** before the next stage. (Verified: drops GPU to ~0.5GB.)
2. **Enhancer (Qwen) runs as a subprocess** → process exit frees its ~6GB RAM cleanly. Runs on CPU so it never competes for VRAM, but DOES compete for the tight 16GB RAM → free ComfyUI first.
3. **Text-encode is the dominant cost** on this box (T5/umT5-class encoders on CPU under RAM pressure ≈ minutes). Highest-value future optimization: cache/reuse text embeddings; prefer smaller/GGUF encoders; few-step models.
4. Per-model GGUF quant + `--lowvram` launch flag live in the registry; ComfyUI is launched once with `--lowvram` (single instance).

## 6. Repo Layout / Ownership Map

```
F:\ImageGen\  (git repo → VizGen)
  plan.md                     kartik-only for §0/§4/§7 structure
  README.md  setup.bat  launch.bat   (Track B/shared — setup & run)
  .gitignore                  excludes models/ engine/ .venv/ node_modules/ outputs/ data/
  backend/
    app/                      Track B (Codex) — API, staged worker, routing
    models_registry.yaml      Track B schema; A/D propose entries via notes
    workflows/                Track A (Grok) — ComfyUI graphs per model/mode
    requirements.txt
  frontend/                   Track C (AGY) — image-only UI (generate/edit), toggles, gallery
  scripts/                    downloaders + helpers (write_model_paths, prompt_enhance, ...)
  engine/comfyui/             gitignored — cloned by setup.bat (Track A owns setup)
  models/                     gitignored — weights (Track A downloads)
  benchmarks/                 Track D harness + Track A results
```

## 7. Current Status & Remaining Work

### ✅ DONE (built & verified this session)
- **Backend product works end-to-end**: FastAPI (:8000) + SQLite queue + worker → ComfyUI (:8188) → gallery. First real generations succeeded.
- **Staged pipeline** (`worker.py`): `enhance → generate → upscale` with `/free` load-release between stages, stage+ETA emitted over WS. Imports clean; migration adds `stage/stage_index/stage_total/eta_seconds` columns.
- **Prompt enhancer**: `scripts/prompt_enhance.py` extended to output **prompt + negative** in one Qwen load; validated (CPU). Backend runs it as a subprocess (auto-release).
- **`/free` release**: verified (GPU → ~0.5GB).
- **Upscale wiring**: `comfy_client.run_upscale()` (fetch output → re-upload as input → RealESRGAN workflow).
- **Frontend**: image/edit-ready progress card shows **stage + message + ETA**; **Enhance** and **Upscale ×4** toggles added; builds clean (Vite).
- **Aux models present**: Qwen2.5-1.5B (works), RealESRGAN.

### 🔧 REMAINING WORK (image-only pivot) — assign per track

#### Track A — Model download, workflows, feasibility  ·  **Grok 4.5 High**  ·  ☑ in progress (2026-08-04)
**Owns**: `models/`, `engine/`, `backend/workflows/`, `benchmarks/results.md`, download scripts in `scripts/`.
- [x] **Delete Wan/video weights** (already gone on disk; ~78GB free).
- [x] Write `scripts/download_image_models.py`: Z-Image Turbo GGUF Q3/Q4 + qwen_3_4b TE + ae; FLUX Kontext Q3_K_S + clip_l + t5xxl_fp8 + ae.
- [x] Author workflows: `z_image_turbo_t2i_api.json`, `flux_kontext_edit_api.json` (+ aux upscale docs).
- [x] Smoke **Z-Image Turbo Q4_K_M** generate @512² / 8 steps — **OK** ~495s wall. Kontext edit smoke **pending** (workflow authored; weights on disk).
- [x] Propose registry entries in `benchmarks/results.md` for Track B (enable `z-image-turbo` + `flux-kontext-dev`).

#### Track B — Backend: modes, routing, registry, remove video  ·  **Codex (GPT-5.5 medium)**  ·  ✅ core complete · 🔧 NEW job: gen-model expansion (see below)
**Owns**: `backend/app/`, `models_registry.yaml`, `setup.bat`, `launch.bat`, `README.md`. *(kartik expanded lane 2026-08-04: also owns the FLUX-dev + Qwen-Image add/benchmark job below.)*
- [x] **Remove video** from backend — complete strip per §4.2:
  - [x] Deleted the `t2v/i2v/video → 410` block in `main.py`; `JobCreate.mode` is now `Literal["generate","edit"]` only.
  - [x] Purged stale `umT5`/video/Wan comments in `worker.py` and `comfy_client.py`.
  - [x] Confirmed no `frames`/`fps`/VHS handling remains in `comfy_client.py`/`JobCreate`.
  - [x] Kept image-upload plumbing only as the **edit** (Kontext) input path.
- [x] Add modes: **`generate`** (text→image) and **`edit`** (image+instruction→image). Legacy aliases are no longer accepted after the 2026-08-04 redefinition.
- [x] **Task routing (§4 Rule 4)**: `edit` mode always uses the Kontext model; `generate` uses the selected model. Model chosen internally by mode, not just the dropdown.
- [x] Registry schema: add `task: generate|edit` per model; image-only defaults (width/height/steps/cfg/sampler). Merge Track A/D proposals. Registry must contain **only** image/edit models (no Wan).
- [x] Update `setup.bat` to call the new `download_image_models.py` (not the Wan downloader); ensure `launch.bat` still starts engine+backend+UI.

**NEW — kartik-assigned to Codex 2026-08-04 (cross-track OK per §0): add more generation models + benchmark.**
Expand the `generate` dropdown beyond Z-Image with the two optional models from §4 Rule 2. Owns this end-to-end (download → workflow → registry → benchmark):
- [x] **Extend `scripts/download_image_models.py`** with:
  - **FLUX.1-dev GGUF** — `city96/FLUX.1-dev-gguf` (e.g. `flux1-dev-Q4_K_S.gguf` → `models/unet/`). **Reuses the already-downloaded** `t5xxl_fp8_e4m3fn` + `clip_l` + `ae.safetensors` — no new encoder/VAE needed.
  - **Qwen-Image GGUF** (+ Lightning LoRA for 4–8 step) — find the current GGUF repo (e.g. `city96`/`QuantStack` Qwen-Image); needs its own Qwen2.5-VL text encoder + VAE (fetch those too). Verify exact HF filenames with `HfApi().list_repo_files` first (that's how Z-Image/Kontext filenames were nailed).
- [ ] **Author workflows** `backend/workflows/flux1_dev_t2i_api.json` and `qwen_image_t2i_api.json` (token placeholders `${prompt}/${negative_prompt}/${width}/${height}/${seed}/${steps}/${cfg}/${sampler}/${scheduler}`, same pattern as `z_image_turbo_t2i_api.json`).
- [ ] **Registry**: add `flux-dev` + `qwen-image` entries (`task: generate`, GGUF paths, per-model defaults, `--lowvram`). Keep **Q4_K_M-class** quants (Track D benchmark showed Q3≈Q4 on VRAM — quant doesn't buy headroom; resolution does).
- [ ] **Benchmark** both with `benchmarks/zimage_bench.py` (adapt the MATRIX to point at each workflow) across 512²/768²/1024²; append VRAM peak + wall time to `benchmarks/results.md`. Expect FLUX-dev (12B) to be **slow + tight** (heavy offload); default it to 768² and label "max quality, slow".
- **Heads-up from Track D**: on this 4GB/16GB box, **1024² thrashes (52s/step, 94% VRAM)** and the **CPU text-encode dominates cold latency** — set conservative defaults (768², few steps) and expect FLUX-dev minutes-per-image.

#### Track C — Frontend: image-only, edit mode, upload  ·  **AGY (Sonnet 4.6 thinking)**  ·  ✅ complete 2026-08-04
**Owns**: `frontend/`.
- [x] Remove video modes (t2v/i2v) from UI — modes are now **Generate** and **Edit** at the top level.
- [x] **Edit UI**: image upload drag-drop zone + "instruction" textarea; submits `mode:"edit"` with `init_image` (base64). Edit uses FLUX.1 Kontext implicitly (no model dropdown in edit mode).
- [x] Model dropdown shows only `task:generate` models (filtered by `m.task === 'generate'` in GeneratePage) — §4 Rule 4.
- [x] Enhance / Upscale toggles kept in shared "Pipeline Options" card with descriptive subtext.
- [x] Stage+ETA progress card kept (LiveProgress) — added `edit` stage label.
- [x] Gallery mode filters updated: All / Generated / Edited (removed t2v/i2v).
- [x] "Edit this" button on output panel: loads output image directly into Edit mode.
- [x] Sidebar nav updated to "Generate & Edit". Prompt tips updated (no video tips).
- [x] Production build: ✅ `226KB JS · 15KB CSS · 258ms`.

#### Track D — Perf / quant / pipeline orchestration  ·  **Claude (Opus 4.8)**  ·  🔄 in progress
**Owns**: `benchmarks/bench.py`, tuning notes, staged-pipeline orchestration in `worker.py`/`comfy_client.py` (co-owned handoff w/ Track B).
- [x] Staged load-release pipeline + enhancer/upscale wiring + ETA (done).
- [ ] Validate CPU-offload/residency for FLUX Kontext + Z-Image GGUF on 4GB; per-model launch flags.
- [ ] Text-embedding reuse / smaller encoder investigation (top latency win, §5.3).
- [ ] Tune ETA constants per model from Track A benchmarks.

### Cross-cutting (after the above)
- [ ] `setup.bat`/`launch.bat`/`README`/`.gitignore` finalized for image-only; **git push to VizGen** (code+setup only; weights/engine/venv excluded). *(scaffold already written; update model list + remove video mentions.)*

## 8. Milestones
1. **M1 — Clean image-only base**: video removed (code+weights), Z-Image Turbo generating via the dropdown end-to-end.
2. **M2 — Editing**: FLUX.1 Kontext edit mode working (image + instruction → edited image).
3. **M3 — Full feature stack**: enhance + upscale composed with generate/edit in the staged pipeline, stage+ETA in UI.
4. **M4 — Multi-model**: additional gen models (Qwen-Image, FLUX.1-dev) selectable.
5. **M5 — Ship**: setup.bat/launch.bat one-command run; GitHub push; docs.

## 9. Risks
- **Model feasibility on 4GB is unproven** for the new models — each needs a real smoke test (multi-GB download + slow first run). Z-Image Turbo (6B, few-step) is the safest bet; FLUX-class (12B) will be slow and tight.
- **RAM (16GB), not just VRAM**, is a real limiter (text encoders + pinned mem) — the load-release discipline is mandatory.
- **Download size/time**: several GGUF models + encoders = tens of GB. Confirm disk (currently ~44GB free; +45GB after deleting Wan).
- **Quality expectation**: near-SOTA, not literal ChatGPT/Nano-Banana — communicated to kartik.

## 10. Notes Log
*(Append-only, dated, terse. Edit only your own entries. Proposals to change §0/§4/§7 wait for kartik.)*

- **2026-08-04 (Claude/Track D) — PIVOT captured**: Rewrote plan for image-only per kartik. Decisions locked: delete video entirely + Wan weights; multi-model image dropdown (Z-Image Turbo primary, Qwen-Image, FLUX.1-dev); **FLUX.1 Kontext [dev]** for text-instruction editing; backend picks model by task. Staged enhance/generate/edit/upscale load-release pipeline already built & reusable. Prior video/Wan learnings archived below.
- **2026-08-04 (Codex/Track B) — initial image-only backend pivot**: Added `generate`/`edit` routing, with `edit` internally selecting the enabled `task: edit` model and requiring `init_image`. Replaced Wan registry with image/edit-only schema placeholders (Z-Image Turbo, Qwen-Image Lightning, FLUX.1-dev, FLUX.1 Kontext), all disabled until Track A supplies workflows/paths/smoke data. Removed VideoHelperSuite setup, refreshed README for image-only, kept staged enhance/generate-or-edit/upscale worker intact. Later reopened cleanup below supersedes the temporary compatibility behavior from this pass.
- **2026-08-04 (Claude/Track D) — FULL PRODUCT E2E VALIDATED** ✅: One `POST /api/jobs` (z-image-turbo, generate, 768², `enhance_prompt+upscale`) ran the complete staged pipeline through the real backend: **enhance (Qwen rewrote prompt + auto-negative, released) → generate (Z-Image 768², /free) → upscale (RealESRGAN ×4 → 3072², /free) → gallery**. Live stage/progress/ETA/message worked end-to-end (`enhance 1/3` → `Inferencing step 7/8` → `done 3/3`). Output = gorgeous near-SOTA 3072² mountain-lake (`benchmarks/e2e_result.png`). ~10min total (CPU text-encode dominates; sampling+upscale fast). **The core product is proven working.** Remaining to ship: honest edit-mode ETA in UI (Track C), ETA-constant tuning (Track D), and the git push.
- **2026-08-04 (Claude/Track D) — FLUX Kontext editing: WORKS but impractically slow on 4GB**: Ran `flux_kontext_edit_api.json` directly (apple → snowy-forest background, 20 steps). **Graph is valid** (no node errors; DualCLIP flux, FluxKontextImageScale, ReferenceLatent, FluxGuidance all load + sample). **BUT**: Kontext Q3_K_S is a **12B model / ~5GB > 4GB VRAM → 0MB resident, full offload → ~116s/step** (same physical wall as the old Wan A14B). That's **~40min for a 20-step edit** (~23min @12 steps, ~15min @8). Also: the 12B model + t5xxl strains the 16GB box (my poll loop hit `bash: fork: Resource temporarily unavailable`). **Conclusion**: editing is functionally correct but a **"slow tier" on 4GB** — not interactive. Options for kartik: (a) accept + label "editing ~15-40min" in UI; (b) try **Q2_K (4.0GB) + ~12 steps** to shave time (still thrashes, marginal); (c) a Kontext Lightning/turbo LoRA if one exists (few-step edit). Interrupted the run to free the machine; no sample edit captured (would've cost ~30min). Registry: keep `flux-kontext-dev` enabled but Track C should surface an honest ETA/warning for edit mode.
- **2026-08-04 (Claude/Track D, relaying kartik) — gen-model expansion assigned to Codex**: kartik assigned the "add FLUX.1-dev + Qwen-Image and benchmark them" job to **Codex/Track B** (normally Track A/D lanes — cross-track OK per §0). Full spec added to §7 Track B. Track D's benchmark data (below) is the guidance: Q4-class quants, 768² defaults, 1024² thrashes on 4GB. Claude/Track D does NOT own this job now.
- **2026-08-04 (Claude/Track D) — Z-Image benchmark (Q4 vs Q3 × 512/768/1024)**: Full matrix in `benchmarks/zimage_benchmark.md`, samples crisp near-SOTA photoreal. Findings: (1) **Resolution is the dominant cost, not quant** — 512²≈2.1GB/~3min, 768²≈2.8GB/~3.5min, **1024²≈3.8GB (94% VRAM!) / ~7min thrash @52s/step** (weights can't stay resident at 1024²). (2) **Q3_K_S ≈ Q4_K_M** on VRAM peak (2127 vs 2129 @512; both 2785 @768; both 3785 @1024) and time — peak is **activation-bound**, so Q3 buys nothing; **use Q4_K_M** (slightly sharper). (3) **Recommend default 768², cap interactive at 768²; label 1024² "slow"** in the UI/registry. (4) Encoder eviction under RAM pressure re-encodes each run (~150s) → embedding cache is the top latency win. Registry: `z-image-turbo` Q4_K_M, default 768²/8 steps/cfg 1.0/euler-simple.
- **2026-08-04 (Claude/Track D) — Z-Image Turbo VALIDATED on 4GB**: Ran `z_image_turbo_t2i_api.json` (Grok's graph) directly on ComfyUI. **Works, no node errors** (`lumina2` CLIP type for qwen_3_4b is correct; `ModelSamplingAuraFlow` shift 3.0). Output is **crisp near-SOTA photorealism** (see `benchmarks/zimage_result.png` — an apple smoke, and a clean run). **Timing**: 493s total cold @1024²/8 steps — of which **sampling only ~83s (8×10.4s/step)**; the rest (~410s) is the 5.3GB Qwen3-4B encoder loading/encoding on CPU (the recurring text-encode tax). Warm ≈ ~2min. Partial GGUF load (1062MB resident/3771MB offloaded) fits 4GB. **Contention warning**: when multiple agents hit the single 4GB GPU at once, runs collapse to full offload (0MB resident, **52s/step**). Production backend queue serializes jobs, so this only bites ad-hoc concurrent tests — agents should NOT run generations simultaneously. FLUX Kontext edit graph exists (Grok) but not yet validated by Track D. ETA constants for `worker.py`: z-image cold ~500s, warm ~120s.
- **2026-08-04 (Claude/Track D, relaying kartik directive)**: kartik confirmed video is **permanently removed — "never returning."** Requesting a **complete strip, not 410 deprecation stubs** (§4.2 updated, Track B reopened for residual cleanup). Verified Wan/video **weights are deleted** (models/unet, vae, umT5 all gone; only image/edit + aux weights remain). Residual backend items for Codex: remove the `main.py` 410 video block + `t2v/i2v` from `JobCreate.mode`; purge stale umT5/video comments in `worker.py`/`comfy_client.py`. No code owned by Track B was edited by Track D — this is a plan/scope update per kartik.
- **2026-08-04 (Codex/Track B) — reopened strip complete**: Removed the 410 compatibility branch and all legacy aliases from `JobCreate`; API mode is now exactly `Literal["generate","edit"]`. Cleaned stale backend comments/docs/registry wording and changed old DB migration default to `generate`. Verified Track B-owned stale scan is clean, backend compile passes, and API contract returns: health 200, models `[]`, generate with disabled registry 404, edit without `init_image` 400, legacy `t2v`/`t2i` 422 schema rejection.
- **Prior (pre-pivot) key learnings kept for reference**: (a) Product works E2E (FastAPI→queue→ComfyUI→gallery). (b) Text-encode on CPU (~10min) dominated latency at 16GB RAM — favor few-step models + embedding reuse. (c) torch.compile/Triton NO-GO on Windows/Turing. (d) `/free` releases VRAM to ~0.5GB. (e) On 4GB, a single A14B Q2_K expert (5GB) > VRAM — informed the "GGUF + one-model-at-a-time" rule. (f) ffmpeg + RealESRGAN available. Full pre-pivot Wan benchmark data remains in `benchmarks/results.md` for historical reference.
- **2026-08-04 (AGY/Track C) — pivot complete**: Rewrote `frontend/` for image-only. Key changes: (1) Top-level mode switch replaced t2i/t2v/i2v — now **Generate** (text→image, model dropdown) and **Edit** (image upload + instruction, Kontext implicit). (2) Model dropdown filtered to `task:generate` only per §4 Rule 4. (3) Edit UI: drag-drop image zone + instruction textarea → submits `mode:"edit"` + `init_image`. (4) "Edit this" button on output panel auto-loads output into Edit mode. (5) Pipeline Options card (enhance/upscale toggles) shared across both modes. (6) Gallery filters: All/Generated/Edited. (7) LiveProgress stage labels extended with `edit`. (8) useModels fallback updated to Z-Image Turbo + FLUX.1-dev (image-only). Build: 226KB JS · 258ms. Dev server: http://127.0.0.1:5174/

- **2026-08-04 (Grok/Track A, image pivot)**: Wan gone. Aux enhance+upscale kept (upscale via `scripts/upscale_image.py` in backend; worker modes generate/edit). Downloaded Z-Image Turbo Q4_K_M+Q3_K_S + qwen_3_4b_fp8 TE; Kontext Q3_K_S + clip_l + t5xxl_fp8 + ae already present. Workflows: `z_image_turbo_t2i_api.json`, `flux_kontext_edit_api.json`. **Z-Image smoke PASS** ~495s @512/8steps. Registry proposals in results.md � Track B enable. Kontext edit smoke still open.

- **2026-08-04 (Codex/Track B) - gen-model expansion smoke complete**: Extended scripts/download_image_models.py with FLUX.1-dev (city96/FLUX.1-dev-gguf, flux1-dev-Q4_K_S.gguf) and Qwen-Image (city96/Qwen-Image-gguf, qwen-image-Q4_K_M.gguf) plus Qwen2.5-VL FP8 TE, Qwen VAE, and Lightning 8-step LoRA. Downloaded all files to models/. Added z_image_turbo_generate_api.json, flux_dev_generate_api.json, qwen_image_lightning_generate_api.json; registry now enables Z-Image, Qwen-Image Lightning, FLUX-dev, and Kontext edit with concrete paths. Smoke: Qwen 512x512/4-step PASS, 2793 MB peak, 928.6s; FLUX-dev 512x512/4-step PASS, 2995 MB peak, 561.0s. Full 512/768/1024 matrix deferred as unattended long run; see benchmarks/generate_model_smoke.md and benchmarks/results.md.
