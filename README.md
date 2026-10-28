# VizGen

A local image-generation and instruction-editing workbench built with React, FastAPI, and ComfyUI. A persistent job queue runs generation, optional prompt enhancement, and upscaling in stages to reduce simultaneous memory use.

The development target is a Windows 11 laptop with a GTX 1650 Ti (4 GB) and 16 GB system RAM. Reported results describe that setup; other environments need separate validation.

## Implementation

- Registry-driven model selection and ComfyUI workflow graphs.
- SQLite job persistence, a single worker, progress events, and a gallery.
- Sequential model loading/release between generation and post-processing stages.
- Optional CPU prompt rewriting with Qwen2.5 and RealESRGAN upscaling.

The application currently handles images. Model-training code and video generation are outside its current scope.

## Inspect before downloading models

[ARCHITECTURE.md](ARCHITECTURE.md) explains the worker and memory strategy. [BENCHMARKS.md](BENCHMARKS.md) records timings and measurement limits.

To inspect/build the frontend without downloading weights:

```bash
git clone https://github.com/Kartik-A-1820/VizGen.git
cd VizGen/frontend
npm ci
npm run build
npm run lint
```

Use a Node.js version compatible with the Vite version in `package.json`. The UI can build independently; generation requires the backend, ComfyUI, custom nodes, and model artifacts.

## Run the full application on Windows

Prerequisites: Python 3.10 or 3.11, Git, Node.js/npm, a compatible NVIDIA driver, and disk space for model weights and caches.

From the repository root:

```bat
setup.bat
launch.bat
```

Read `setup.bat` first. It creates a venv, installs the backend and a fixed CUDA PyTorch build, clones ComfyUI/custom nodes, and downloads several model families and auxiliary weights. The combined download is substantial and has no fixed size guarantee. Upstream clones and some Python dependencies are not pinned; this is not a locked reproduction environment.

The setup accepts an optional `HF_TOKEN`. Access depends on the selected model's availability and terms; a token does not guarantee download speed. Never put a token in an issue or commit.

`launch.bat` opens three service terminals:

| Service | Address |
| --- | --- |
| ComfyUI engine | `http://127.0.0.1:8188` |
| FastAPI backend | `http://127.0.0.1:8000` |
| Vite frontend | `http://localhost:5173` |

Wait for the engine and API to become ready. For a first generation, use the default model, a modest resolution, and disable enhancement/upscaling. Check the saved output and job status before enabling the full staged pipeline. Close the service terminals to stop them.

The launch workflow is Windows-specific. The individual Python/npm processes can be adapted elsewhere, but a portable setup is not established by these scripts.

## Models and measurements

`backend/models_registry.yaml` drives the available tasks. Configured families include Z-Image Turbo, Qwen-Image, FLUX.1-dev, and FLUX.1 Kontext. Their model licenses and access terms are separate from this repository.

The repository reports approximately **188 s at 512²** and **202 s at 768²** for its Z-Image configuration on the reference laptop. Cold/warm loading, sampling, and full-pipeline timings must be distinguished; see the benchmark notes. Some other models were only smoke-tested.

Output inspection is qualitative. No standardized image-quality or prompt-adherence benchmark establishes a model ranking here. Timing results are not a universal speed or memory guarantee.

## Source map

| Path | Responsibility |
| --- | --- |
| `backend/app/` | API, persistent queue, staged worker |
| `backend/models_registry.yaml` | Task/model registry |
| `backend/workflows/` | ComfyUI graphs |
| `frontend/` | Job submission, progress, gallery |
| `scripts/` | Download and workflow utilities |
| `benchmarks/` | Recorded runs and measurement scripts |

See [frontend/README.md](frontend/README.md) for UI development and [local.example/README.md](local.example/README.md) for machine-specific registry overlays. Keep weights, caches, generated images, databases, and local credentials out of commits.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). Useful work includes pinned engine/custom-node revisions, queue/error-path tests, portable installation, reproducible cold/warm measurements, and a documented image-evaluation protocol.

No standalone LICENSE file is included. Check repository and model reuse terms before redistribution.
