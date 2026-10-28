# VizGen frontend

React/Vite interface for job submission, progress, and the output gallery.

From this directory:

```bash
npm ci
npm run dev
```

Use Node.js compatible with the locked Vite toolchain. The development server listens on port 5173 and proxies `/api` and `/ws` to the backend on port 8000; see `vite.config.js`.

`npm run build` checks the production bundle and `npm run lint` runs Oxlint. A successful build does not validate generation: the API, ComfyUI, model registry, custom nodes, and weights must also be ready.

For UI changes, check job submission, queued/running/failed/completed states, reconnect behavior, and gallery rendering against the local backend. Include screenshots for visible changes. See [CONTRIBUTING.md](../CONTRIBUTING.md) and the [root README](../README.md).
