/**
 * useModels — Fetch model registry from backend and normalise the shape.
 * Track C — AGY
 *
 * Backend returns:
 *   { id, name, label, tier, vram_tier, modes, defaults, defaults_by_mode, ... }
 *
 * We normalise to:
 *   { id, name, tier, vram_tier, modes, defaults,          ← flat (for current mode)
 *     defaults_by_mode,                                    ← per-mode overrides
 *     ui_note }
 */
import { useState, useEffect } from 'react';
import { fetchModels } from '../api.js';

// Fallback demo models — image-only, matches new registry schema
const FALLBACK_MODELS = [
  {
    id: 'z-image-turbo',
    name: 'Z-Image Turbo (6B)',
    label: 'Z-Image Turbo (6B) — fast',
    tier: 'fast',
    task: 'generate',
    vram_tier: '≤4GB',
    modes: ['generate'],
    defaults: { width: 512, height: 512, steps: 12, cfg: 5.0 },
    defaults_by_mode: {
      generate: { width: 512, height: 512, steps: 12, cfg: 5.0 },
    },
    ui_note: 'Few-step turbo model — fastest on 4GB.',
  },
  {
    id: 'flux-dev-q4',
    name: 'FLUX.1-dev Q4_K_M',
    label: 'FLUX.1-dev Q4_K_M — quality',
    tier: 'quality',
    task: 'generate',
    vram_tier: '4GB+offload',
    modes: ['generate'],
    defaults: { width: 512, height: 512, steps: 20, cfg: 3.5 },
    defaults_by_mode: {
      generate: { width: 512, height: 512, steps: 20, cfg: 3.5 },
    },
    ui_note: 'Best prompt adherence. Slow on 4GB (~5–10 min).',
  },
];

/** Normalise a raw model object from the API into a consistent frontend shape. */
function normalise(m) {
  return {
    id:               m.id,
    name:             m.name || m.label || m.id,
    label:            m.label || m.name || m.id,
    tier:             m.tier ?? 'fast',
    task:             m.task ?? 'generate',
    vram_tier:        m.vram_tier ?? '',
    modes:            m.modes ?? ['generate'],
    defaults_by_mode: m.defaults_by_mode || { generate: m.defaults },
    defaults:         m.defaults_by_mode?.generate ?? m.defaults_by_mode?.t2i ?? m.defaults ?? {},
    ui_note:          m.ui_note ?? '',
  };
}

export function useModels() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchModels()
      .then((data) => {
        if (!cancelled) {
          const list = Array.isArray(data) && data.length > 0 ? data : FALLBACK_MODELS;
          setModels(list.map(normalise));
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModels(FALLBACK_MODELS);
          setError('Backend offline — showing default models');
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, []);

  return { models, loading, error };
}
