# Contributing to VizGen

Choose a specific UI, queue, workflow, or reproducibility problem. Discuss a new model family or pipeline stage in an issue before adding large dependencies or downloads.

## Validation

- Frontend: from `frontend/`, run `npm ci`, `npm run build`, and `npm run lint`.
- Workflow changes: run the relevant smoke script against a prepared local ComfyUI instance and inspect the saved output. State the engine/custom-node commits and model files used.
- Queue/API changes: describe successful, failed, cancelled, and restarted-job behavior; include focused tests where practical.

There is no comprehensive offline backend test suite. A frontend build or valid workflow JSON does not establish end-to-end generation.

For benchmarks, record the commit, engine/custom-node revisions, model/quantization, workflow, sampler, steps, seed, resolution, hardware, and package versions. Separate cold loading, warm sampling, and full-pipeline time. Preserve raw observations and label visual preferences as qualitative.

Do not commit weights, tokens, generated databases, private input images, or model caches. Use the local registry overlay for machine-specific paths.

A pull request should explain the problem, implementation, commands/results, and untested paths. No standalone LICENSE file is present; identify model and third-party terms in proposed additions.
