/**
 * ImageGen API client
 * Connects to FastAPI backend at localhost:8000
 * Track C — AGY
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const WS_BASE  = BASE_URL.replace(/^http/, 'ws');

// ── Helpers ──────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const res = await fetch(`${BASE_URL}${path}`, { ...opts, headers });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// ── Models registry ───────────────────────────────────────

/**
 * Fetches the model list from /api/models
 * Shape: Array<{ id, name, task, tier, modes, defaults: { width, height, steps, cfg }, vram_tier }>
 */
export async function fetchModels() {
  return apiFetch('/api/models');
}

// ── Job submission ────────────────────────────────────────

/**
 * Submit an image generation or instruction-editing job.
 * @param {Object} params
 * @param {string} params.model_id
 * @param {string} params.mode          - 'generate' | 'edit'
 * @param {string} params.prompt
 * @param {string} [params.negative]
 * @param {number} params.width
 * @param {number} params.height
 * @param {number} params.steps
 * @param {string} [params.init_image]  - data URL for edit mode
 * @param {number} [params.seed]        - -1 for random
 * @returns {Promise<{ job_id: string, position: number }>}
 */
export async function submitJob(params) {
  return apiFetch('/api/jobs', { method: 'POST', body: JSON.stringify(params) });
}

// ── Job status polling ────────────────────────────────────

/**
 * Get current job status.
 * Returns: { job_id, status: 'queued'|'running'|'done'|'failed', position, progress, output_url, error }
 */
export async function getJobStatus(jobId) {
  return apiFetch(`/api/jobs/${jobId}`);
}

/**
 * Cancel a queued (not yet running) job.
 */
export async function cancelJob(jobId) {
  return apiFetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
}

// ── Queue ─────────────────────────────────────────────────

/**
 * Get the full job queue (queued + currently running).
 * Returns: Array<{ job_id, status, position, prompt, model_id, mode, submitted_at }>
 */
export async function fetchQueue() {
  return apiFetch('/api/queue');
}

// ── Gallery / History ─────────────────────────────────────

/**
 * Fetch completed generation history (gallery).
 * @param {number} [page=1]
 * @param {number} [per_page=24]
 * @returns {{ items: Array, total: number, page: number, per_page: number }}
 */
export async function fetchGallery({ page = 1, per_page = 24 } = {}) {
  return apiFetch(`/api/gallery?page=${page}&per_page=${per_page}`);
}

/**
 * Delete a gallery item.
 */
export async function deleteGalleryItem(itemId) {
  return apiFetch(`/api/gallery/${itemId}`, { method: 'DELETE' });
}

/**
 * Get the absolute URL for a media file served by the backend.
 */
export function mediaUrl(relativePath) {
  if (!relativePath) return null;
  if (relativePath.startsWith('http')) return relativePath;
  return `${BASE_URL}${relativePath}`;
}

// ── WebSocket progress ────────────────────────────────────

/**
 * Open a WebSocket connection for real-time job progress.
 *
 * Fires callbacks:
 *   onProgress({ progress: 0–100, step, total_steps, preview_url })
 *   onDone({ output_url })
 *   onError(errorMessage)
 *
 * Returns a close() function.
 */
export function openJobSocket(jobId, { onProgress, onDone, onError } = {}) {
  const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}`);

  ws.addEventListener('message', (evt) => {
    let data;
    try { data = JSON.parse(evt.data); } catch { return; }

    switch (data.type) {
      case 'progress':
        onProgress?.(data);
        break;
      case 'done':
        onDone?.(data);
        ws.close();
        break;
      case 'error':
        onError?.(data.message || 'Unknown error');
        ws.close();
        break;
    }
  });

  ws.addEventListener('error', () => onError?.('WebSocket connection failed'));

  return () => ws.readyState <= WebSocket.OPEN && ws.close();
}

/**
 * Open a WebSocket to the global queue channel.
 * Fires onUpdate(queueSnapshot) whenever the queue changes.
 * Returns a close() function.
 */
export function openQueueSocket({ onUpdate } = {}) {
  const ws = new WebSocket(`${WS_BASE}/ws/queue`);
  ws.addEventListener('message', (evt) => {
    let data;
    try { data = JSON.parse(evt.data); } catch { return; }
    onUpdate?.(data);
  });
  return () => ws.readyState <= WebSocket.OPEN && ws.close();
}
