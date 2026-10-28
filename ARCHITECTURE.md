# VizGen — Architecture & Design Decisions

VizGen is a local image-generation and instruction-editing workbench built around a 4 GB development GPU. This document describes the orchestration and memory tradeoffs used on that reference machine.

---

## 1. System Overview

Three processes cooperate: a **web UI**, a **FastAPI orchestration backend** (queue + staged pipeline + model registry), and a **headless ComfyUI engine** that actually runs the diffusion models. A small **CPU-only LLM** handles prompt enhancement out-of-band so it never competes for the GPU.

```mermaid
flowchart TB
    subgraph Client
        UI["Web UI — React/Vite<br/>:5173<br/>generate · edit · gallery · live progress"]
    end

    subgraph Backend["FastAPI backend — :8000"]
        API["REST + WebSocket API"]
        Q[("SQLite job queue<br/>single worker")]
        REG["Model registry<br/>models_registry.yaml<br/>(drives the dropdown)"]
        W["Staged worker<br/>enhance → generate/edit → upscale"]
    end

    subgraph Engine["Inference — one model resident at a time"]
        CU["ComfyUI — :8188<br/>--lowvram · GGUF loader"]
        QW["Qwen2.5-1.5B<br/>CPU subprocess"]
    end

    subgraph Disk["Local weights (GGUF)"]
        M["Z-Image Turbo · Qwen-Image · FLUX.1-dev<br/>FLUX.1 Kontext · encoders · VAE · RealESRGAN"]
    end

    UI -->|"REST /api/jobs"| API
    UI <-->|"WebSocket: stage, progress, ETA"| API
    API --> Q --> W
    W --> REG
    W -->|"submit graph, /free between stages"| CU
    W -->|"subprocess (enhance)"| QW
    CU --> M
    CU -->|"/view outputs"| API
    API -->|"gallery"| UI
```

**Why a FastAPI layer in front of ComfyUI** instead of using ComfyUI directly: the backend provides a persistent queue, model registry, staged jobs, and progress events above the inference engine.

**Why ComfyUI as the engine** instead of raw `diffusers`: it exposes the low-VRAM execution, tiled VAE, GGUF custom-node support, and HTTP/WebSocket interfaces used by these workflows. This is a project design choice, not a comparative engine benchmark.

---

## 2. The Job Lifecycle (staged, load-use-release)

Every request is a sequence of stages. Each stage **loads its model, runs, and releases it before the next stage starts** — the single most important pattern for fitting a multi-model workflow into 4 GB. Stages are optional except the core generate/edit.

```mermaid
sequenceDiagram
    participant UI
    participant API as FastAPI
    participant W as Worker
    participant QW as Qwen (CPU)
    participant CU as ComfyUI (GPU)

    UI->>API: POST /api/jobs {model, mode, prompt, enhance?, upscale?}
    API->>API: enqueue (SQLite), return job_id
    UI-->>API: open WebSocket(job_id)

    Note over W: Stage 1 — Enhance (optional)
    W->>CU: POST /free  (release GPU → RAM for Qwen)
    W->>QW: subprocess: enhance prompt + negative
    QW-->>W: enhanced prompt / negative
    W-->>UI: stage=enhance 1/3, ETA

    Note over W: Stage 2 — Generate or Edit
    W->>CU: POST /free
    W->>CU: submit workflow graph (selected/edit model)
    CU-->>W: progress (per sampling step)
    W-->>UI: stage=generate 2/3, "step k/N", ETA
    CU-->>W: output image

    Note over W: Stage 3 — Upscale (optional)
    W->>CU: POST /free  (release gen model → VRAM for RealESRGAN)
    W->>CU: RealESRGAN ×4 on the generated image
    CU-->>W: upscaled output
    W-->>UI: stage=upscale 3/3

    W->>API: status=done, outputs[]
    API-->>UI: done → gallery
```

Key point: **the enhancer runs as a separate OS process**. When it exits, the OS reclaims its ~6 GB of RAM cleanly — no manual memory management, and it never touches the GPU (it's CPU-only), so the GPU stays free for the diffusion model that follows.

---

## 3. Memory Discipline — the core of the 4 GB design

On a 4 GB card, you cannot hold two models at once. The whole system is organized around **one resident model, explicitly released between stages**.

```mermaid
flowchart LR
    A["Idle<br/>~0.5 GB"] -->|enhance requested| B["Load Qwen (CPU RAM)"]
    B -->|done| C["/free + process exit<br/>→ back to idle"]
    C -->|generate| D["Load gen model<br/>GGUF, partial GPU + CPU offload"]
    D -->|sampled| E["/free<br/>unload + free VRAM"]
    E -->|upscale| F["Load RealESRGAN"]
    F -->|done| G["/free → Idle"]

    style A fill:#1f6f3f,color:#fff
    style C fill:#7a5c00,color:#fff
    style E fill:#7a5c00,color:#fff
    style G fill:#1f6f3f,color:#fff
```

Mechanisms:
- **`POST /free {unload_models, free_memory}`** to ComfyUI between every stage — verified to drop the GPU back to ~0.5 GB.
- **`--lowvram`** keeps only the actively-executing sub-module on the GPU and streams the rest from CPU RAM (pinned memory) — this is how a 5–7 GB model "runs" on a 4 GB card.
- **GGUF quantization** (Q4/Q5) shrinks the weights on disk and in memory so partial residency is even possible.
- **Single-worker queue**: exactly one job touches the GPU at a time. With one GPU there is no parallelism to exploit, and concurrent jobs would just thrash — the SQLite queue serializes everything.

---

## 4. Task Routing — the model is chosen by the task

The UI exposes *generate* and *edit*. The backend picks the actual model internally, so features compose without the user wiring them together.

```mermaid
flowchart TD
    J["Job (mode, model_id, flags)"] --> EN{"enhance_prompt?"}
    EN -- yes --> ENH["Qwen2.5-1.5B rewrites prompt + negative"]
    EN -- no --> MODE
    ENH --> MODE{"mode?"}
    MODE -- generate --> G["Selected generate model<br/>(Z-Image / Qwen-Image / FLUX-dev)"]
    MODE -- edit --> K["FLUX.1 Kontext<br/>(always, regardless of dropdown)"]
    G --> UP
    K --> UP{"upscale?"}
    UP -- yes --> R["RealESRGAN ×4"]
    UP -- no --> OUT["Output → gallery"]
    R --> OUT
```

The dropdown itself is **100 % registry-driven** (`backend/models_registry.yaml`): each entry declares its `task`, GGUF paths, workflow graph, per-model defaults, and launch flags. Adding a model = adding a registry entry + a workflow JSON; no code change.

---

## 5. Design Decisions & Rationale

### Engine & structure
| Decision | Why (given 4 GB / local / open-weight) | Trade-off accepted |
|---|---|---|
| ComfyUI as the inference engine | Best OSS low-VRAM manager + GGUF loader + headless API; no built-in filter | Extra process to manage |
| FastAPI orchestration layer on top | One product surface: queue, gallery, dropdown, staged pipelines, ETA | More moving parts than "just ComfyUI" |
| Registry-driven model list | Add models via YAML + workflow JSON, no code changes | Registry/workflow must stay in sync |
| Single-worker SQLite queue | One GPU → no parallelism; serialization prevents thrash | No concurrent jobs |

### Memory / 4 GB
| Decision | Why | Trade-off |
|---|---|---|
| GGUF-quantized models everywhere | Only way large DiTs fit in/near 4 GB | Slight quality loss vs fp16 |
| `--lowvram` weight streaming | Runs 5–7 GB models on a 4 GB card via CPU offload | Slower per step |
| `/free` between every stage | Reduce simultaneous model residency; explicit release between stages | Cold reload each stage |
| Enhancer as CPU subprocess | Frees ~6 GB RAM on exit; never competes for GPU | Cold LLM load per job |
| **Q4_K_M over Q3** | Benchmarks show VRAM peak is *activation-bound* — Q3 buys no headroom, Q4 is sharper | Marginally larger file |
| **Cap generate at 768²** | 1024² pushes VRAM to 94 % → per-step weight-streaming (~7 min) | Lower max resolution (upscale ×4 recovers pixels) |
| Prefer few-step "turbo/Lightning" models | Fewer steps ≈ far less wall-clock; models that *fit* avoid per-step thrash | Fewer step-count knobs |

### Models
| Decision | Why |
|---|---|
| **Z-Image Turbo** as default generator | Few-step reference configuration with recorded timings and qualitative output inspection |
| FLUX-dev / Qwen-Image as options | Quality alternatives; kept but flagged (heavier, slower) |
| **FLUX.1 Kontext** for editing | Best open instruction-editor; kept as a **slow tier** (12 B > 4 GB → ~15–40 min/edit) |
| Qwen2.5-1.5B (CPU) enhancer / RealESRGAN upscaler | Cheap, CPU-or-light features that compose in the staged pipeline |

### Deployment
| Decision | Why |
|---|---|
| `setup.bat` (one-time) / `launch.bat` (run) | One-command install + run for a non-dev on Windows |
| Weights/engine/venv **gitignored**, recreated by setup | Keep the repo to code + setup only (~0.5 MB, not tens of GB) |
| `local/` private overlay (gitignored) merged by the registry | Machine-only additions never enter the public product |

---

## 6. What we deliberately rejected (and why)

```mermaid
flowchart TD
    V["Video generation (Wan2.2)"] -->|"17 frames already = 94% VRAM;<br/>10s = 160 frames → OOM"| VX["REMOVED — physically infeasible on 4 GB"]
    E["Interactive editing (FLUX Kontext)"] -->|"12B model / 5GB > 4GB VRAM<br/>→ 0 MB resident → ~116 s/step"| EX["KEPT as slow tier (~15–40 min/edit)"]
    T["torch.compile / Triton"] -->|"TritonMissing on Windows/Turing;<br/>bottleneck is memory-bandwidth, not compute"| TX["NO-GO — use torch SDPA"]
    R["1024² generation"] -->|"3785 MB = 94% VRAM,<br/>52 s/step thrash"| RX["Capped at 768²"]

    style VX fill:#7a1f1f,color:#fff
    style TX fill:#7a1f1f,color:#fff
    style RX fill:#7a5c00,color:#fff
    style EX fill:#7a5c00,color:#fff
```

The recurring physics: **any model or activation set larger than ~4 GB cannot stay resident, so it streams every step** — this killed video, makes 12 B editing a slow tier, and caps resolution. It's also why few-step models that *fit* (Z-Image Turbo) are the sweet spot.

The other recurring cost is the **CPU text-encode** (5–6 GB encoders under 16 GB RAM pressure ≈ minutes) — it dominates cold-start latency far more than GPU sampling. The highest-value future optimization is caching/reusing text embeddings.

---

## 7. Data Model

Jobs live in a single SQLite table; the staged-pipeline UI fields (`stage`, `stage_index`, `stage_total`, `eta_seconds`) were added by migration so the frontend can render the progression.

```mermaid
erDiagram
    JOB {
        text   id PK
        text   status "queued|running|succeeded|failed|cancelled"
        text   model_id
        text   mode "generate|edit"
        text   prompt
        text   negative_prompt
        json   params_json "w,h,steps,cfg,seed,enhance_prompt,upscale…"
        real   progress
        text   stage
        int    stage_index
        int    stage_total
        real   eta_seconds
        json   output_json "view URLs"
        text   created_at
        text   finished_at
    }
```

## 8. Component Map

| Concern | Location |
|---|---|
| REST/WebSocket API, job model | `backend/app/main.py` |
| Staged worker (enhance→generate/edit→upscale) | `backend/app/worker.py` |
| ComfyUI client (`/free`, submit, upscale) | `backend/app/comfy_client.py` |
| Job store + migrations | `backend/app/store.py` |
| Model registry loader | `backend/app/registry.py` |
| Model dropdown / defaults | `backend/models_registry.yaml` |
| ComfyUI workflow graphs | `backend/workflows/` |
| Prompt enhancer (CPU LLM) | `scripts/prompt_enhance.py` |
| Web UI | `frontend/src/` |
| Setup / run | `setup.bat`, `launch.bat` |

See **[BENCHMARKS.md](BENCHMARKS.md)** for the measured numbers behind these decisions and **[plan.md](plan.md)** for the project history.
