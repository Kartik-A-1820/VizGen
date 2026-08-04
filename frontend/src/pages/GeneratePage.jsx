/**
 * GeneratePage — image generation + editing (post-pivot, image-only)
 *
 * Modes:
 *   generate — text → image, multi-model dropdown (task:generate models only)
 *   edit     — image + instruction → edited image (FLUX.1 Kontext, implicit)
 *
 * Stages handled by backend: [enhance?] → [generate | edit] → [upscale?]
 * Track C — AGY
 */
import React, { useState, useCallback, useRef } from 'react';
import { useModels } from '../hooks/useModels.js';
import LiveProgress from '../components/LiveProgress.jsx';
import { submitJob, mediaUrl } from '../api.js';

const ASPECT_PRESETS = [
  { label: '1:1',  ratio: [1, 1] },
  { label: '16:9', ratio: [16, 9] },
  { label: '9:16', ratio: [9, 16] },
  { label: '4:3',  ratio: [4, 3] },
];

function resolveSize(ratio, base = 512) {
  const [w, h] = ratio;
  if (w >= h) {
    return { width: base, height: Math.round((base * h / w) / 64) * 64 };
  } else {
    return { width: Math.round((base * w / h) / 64) * 64, height: base };
  }
}

// ── Image upload drop-zone (shared by Generate seed + Edit init) ──────────────
function ImageDropZone({ image, onImage, id, label = 'Drop an image here', required = false }) {
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files[0] || e.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (ev) => onImage(ev.target.result);
    reader.readAsDataURL(file);
  };

  return (
    <div
      id={id}
      onClick={() => inputRef.current?.click()}
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      style={{
        border: `2px dashed ${image ? 'var(--accent)' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius-md)',
        padding: image ? '8px' : '28px',
        cursor: 'pointer',
        textAlign: 'center',
        background: image ? 'var(--accent-dim)' : 'var(--bg-raised)',
        transition: 'border-color var(--dur-fast), background var(--dur-fast)',
        position: 'relative',
      }}
      onMouseEnter={(e) => { if (!image) e.currentTarget.style.borderColor = 'var(--accent)'; }}
      onMouseLeave={(e) => { if (!image) e.currentTarget.style.borderColor = 'var(--border-default)'; }}
      role="button"
      aria-label={label}
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
    >
      {image ? (
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <img
            src={image}
            alt="Uploaded"
            style={{ maxHeight: 180, maxWidth: '100%', borderRadius: 'var(--radius-sm)', display: 'block' }}
          />
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onImage(null); }}
            style={{
              position: 'absolute', top: -8, right: -8,
              background: 'var(--error)', color: '#fff',
              border: 'none', borderRadius: '50%',
              width: 22, height: 22,
              cursor: 'pointer', fontSize: '0.75rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            aria-label="Remove image"
          >✕</button>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: '1.5rem', opacity: 0.4, marginBottom: '6px' }}>🖼</div>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{label}</span>
          {required && <span style={{ color: 'var(--error)', marginLeft: 4 }}>*</span>}
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleDrop}
        id={`${id}-file-input`}
        aria-hidden="true"
      />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function GeneratePage({ onJobSubmitted, toast }) {
  // 'generate' | 'edit'
  const [topMode, setTopMode] = useState('generate');

  // ── Shared fields ─────────────────────────────────────────────────────────
  const [prompt, setPrompt]             = useState('');
  const [enhancePrompt, setEnhancePrompt] = useState(false);
  const [upscale, setUpscale]           = useState(false);
  const [seed, setSeed]                 = useState(-1);

  // ── Generate-mode fields ──────────────────────────────────────────────────
  const { models, loading: modelsLoading, error: modelsError } = useModels();
  // Only show task:generate models in the dropdown (§4 Rule 4)
  const generateModels = models.filter((m) => !m.task || m.task === 'generate');
  const [selectedModelId, setSelectedModelId] = useState('');
  const [aspectRatio, setAspectRatio]   = useState([1, 1]);
  const [steps, setSteps]               = useState(20);
  const [cfg, setCfg]                   = useState(6.0);
  const [negative, setNegative]         = useState('');

  // ── Edit-mode fields ──────────────────────────────────────────────────────
  const [editImage, setEditImage]       = useState(null);   // base64
  const [instruction, setInstruction]   = useState('');

  // ── Job state ─────────────────────────────────────────────────────────────
  const [submitting, setSubmitting]     = useState(false);
  const [activeJobId, setActiveJobId]   = useState(null);
  const [lastOutput, setLastOutput]     = useState(null);
  const [lastOutputMode, setLastOutputMode] = useState('generate');

  // Derive selected model
  const selectedModel = generateModels.find((m) => m.id === selectedModelId) || generateModels[0];

  // Apply per-mode defaults from registry when model changes
  const applyDefaults = (model) => {
    const d = model?.defaults_by_mode?.t2i ?? model?.defaults_by_mode?.generate ?? model?.defaults ?? {};
    if (d.steps != null) setSteps(d.steps);
    if (d.cfg   != null) setCfg(d.cfg);
  };

  const handleModelChange = (id) => {
    setSelectedModelId(id);
    const m = generateModels.find((x) => x.id === id);
    applyDefaults(m);
  };

  React.useEffect(() => {
    if (generateModels.length > 0 && !selectedModelId) {
      handleModelChange(generateModels[0].id);
    }
  }, [generateModels]);

  // Derived image dimensions
  const base = selectedModel?.defaults?.width ?? 512;
  const { width, height } = resolveSize(aspectRatio, base);

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();

    if (topMode === 'generate') {
      if (!prompt.trim()) { toast.error('Please enter a prompt'); return; }
      if (!selectedModel) { toast.error('No model selected'); return; }
    } else {
      // edit mode
      if (!editImage)       { toast.error('Please upload an image to edit'); return; }
      if (!instruction.trim()) { toast.error('Please describe the edit you want'); return; }
    }

    setSubmitting(true);
    setLastOutput(null);

    try {
      let params;
      if (topMode === 'generate') {
        params = {
          model_id: selectedModel.id,
          mode: 'generate',
          prompt: prompt.trim(),
          negative: negative.trim() || undefined,
          width,
          height,
          steps,
          cfg,
          seed: seed === '' ? -1 : Number(seed),
          enhance_prompt: enhancePrompt,
          upscale,
        };
      } else {
        // edit: prompt = instruction, init_image = uploaded image
        params = {
          mode: 'edit',
          prompt: instruction.trim(),
          init_image: editImage,
          enhance_prompt: enhancePrompt,
          upscale,
          seed: seed === '' ? -1 : Number(seed),
        };
      }

      const result = await submitJob(params);
      setActiveJobId(result.job_id);
      setLastOutputMode(topMode);
      onJobSubmitted?.(result);
      toast.info(`Job queued — position ${result.position ?? 1}`);
    } catch (err) {
      toast.error(`Failed to submit: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  }, [topMode, prompt, instruction, editImage, negative, selectedModel, width, height, steps, cfg, seed, enhancePrompt, upscale]);

  const handleDone = useCallback((data) => {
    setLastOutput(data.output_url ? mediaUrl(data.output_url) : null);
    setActiveJobId(null);
    toast.success(lastOutputMode === 'edit' ? 'Edit complete!' : 'Generation complete!');
  }, [lastOutputMode]);

  const isGenerating = submitting || !!activeJobId;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px', alignItems: 'start' }}>

      {/* ── Left: Form ────────────────────────────────────── */}
      <form onSubmit={handleSubmit} id="generate-form" noValidate>

        {/* Top-level mode switch: Generate vs Edit */}
        <div className="card" style={{ marginBottom: '20px' }}>
          <div className="card-body" style={{ padding: '16px' }}>
            <div className="mode-switch" role="group" aria-label="Task mode" style={{ width: '100%', display: 'flex' }}>
              <button
                type="button"
                id="mode-btn-generate"
                className={`mode-btn ${topMode === 'generate' ? 'active' : ''}`}
                style={{ flex: 1 }}
                onClick={() => setTopMode('generate')}
                aria-pressed={topMode === 'generate'}
              >
                ✦ Generate
              </button>
              <button
                type="button"
                id="mode-btn-edit"
                className={`mode-btn ${topMode === 'edit' ? 'active' : ''}`}
                style={{ flex: 1 }}
                onClick={() => setTopMode('edit')}
                aria-pressed={topMode === 'edit'}
              >
                ✎ Edit Image
              </button>
            </div>

            {/* Mode description */}
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '10px', lineHeight: 1.5 }}>
              {topMode === 'generate'
                ? 'Text → image using the selected model.'
                : 'Upload an image, describe what to change — FLUX.1 Kontext will edit it.'}
            </p>
          </div>
        </div>

        {/* ── GENERATE MODE ─────────────────────────────── */}
        {topMode === 'generate' && (
          <>
            {/* Prompt */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <span className="font-semibold">Prompt</span>
                {selectedModel && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className={`badge ${selectedModel.tier === 'fast' ? 'badge-success' : 'badge-accent'}`}>
                      {selectedModel.tier}
                    </span>
                    <span className="badge badge-muted">{selectedModel.vram_tier}</span>
                  </div>
                )}
              </div>
              <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="field-group">
                  <label htmlFor="prompt-input">Positive prompt</label>
                  <textarea
                    id="prompt-input"
                    placeholder="a hyperrealistic portrait of a cyberpunk woman in neon-lit Tokyo rain, detailed face, cinematic lighting…"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    style={{ minHeight: '120px' }}
                  />
                </div>
                <div className="field-group">
                  <label htmlFor="negative-input">
                    Negative prompt
                    <span style={{ color: 'var(--text-muted)', textTransform: 'none', fontWeight: 400 }}> (optional)</span>
                  </label>
                  <textarea
                    id="negative-input"
                    placeholder="blurry, deformed, watermark, low quality…"
                    value={negative}
                    onChange={(e) => setNegative(e.target.value)}
                    style={{ minHeight: '60px' }}
                  />
                </div>
              </div>
            </div>

            {/* Model */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <span className="font-semibold">Model</span>
                {modelsError && <span className="badge badge-warning" title={modelsError}>⚠ fallback</span>}
              </div>
              <div className="card-body">
                <div className="field-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="model-select">Generation model</label>
                  <select
                    id="model-select"
                    value={selectedModelId}
                    onChange={(e) => handleModelChange(e.target.value)}
                    disabled={modelsLoading || generateModels.length === 0}
                  >
                    {modelsLoading && <option value="">Loading models…</option>}
                    {generateModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} — {m.tier} · {m.vram_tier}
                      </option>
                    ))}
                  </select>
                  {selectedModel?.ui_note && (
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '6px' }}>
                      ℹ {selectedModel.ui_note}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Parameters */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <span className="font-semibold">Parameters</span>
              </div>
              <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                {/* Aspect ratio */}
                <div className="field-group">
                  <label>Aspect ratio</label>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                    {ASPECT_PRESETS.map(({ label, ratio }) => {
                      const sel = aspectRatio[0] === ratio[0] && aspectRatio[1] === ratio[1];
                      return (
                        <button
                          key={label}
                          type="button"
                          id={`aspect-${label.replace(':', 'x')}`}
                          className={`btn btn-sm ${sel ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => setAspectRatio(ratio)}
                          aria-pressed={sel}
                        >
                          {label}
                        </button>
                      );
                    })}
                    <span className="font-mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      {width}×{height}px
                    </span>
                  </div>
                </div>

                {/* Steps */}
                <div className="field-group">
                  <label htmlFor="steps-range">
                    Inference steps
                    <span className="slider-value" style={{ float: 'right', marginBottom: 0, textTransform: 'none' }}>{steps}</span>
                  </label>
                  <input type="range" id="steps-range" min={1} max={60} step={1} value={steps} onChange={(e) => setSteps(Number(e.target.value))} />
                </div>

                {/* CFG */}
                <div className="field-group">
                  <label htmlFor="cfg-range">
                    Guidance scale (CFG)
                    <span className="slider-value" style={{ float: 'right', marginBottom: 0, textTransform: 'none' }}>{cfg.toFixed(1)}</span>
                  </label>
                  <input type="range" id="cfg-range" min={1} max={15} step={0.5} value={cfg} onChange={(e) => setCfg(Number(e.target.value))} />
                </div>

                {/* Seed */}
                <div className="field-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="seed-input">Seed <span style={{ color: 'var(--text-muted)', textTransform: 'none', fontWeight: 400 }}>(-1 = random)</span></label>
                  <input type="number" id="seed-input" value={seed} onChange={(e) => setSeed(e.target.value)} min={-1} placeholder="-1" />
                </div>
              </div>
            </div>
          </>
        )}

        {/* ── EDIT MODE ──────────────────────────────────── */}
        {topMode === 'edit' && (
          <>
            {/* Upload */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <span className="font-semibold">Source Image</span>
                <span className="badge badge-info">FLUX.1 Kontext</span>
              </div>
              <div className="card-body">
                <div className="field-group" style={{ marginBottom: 0 }}>
                  <label>Upload image to edit</label>
                  <ImageDropZone
                    id="edit-image-zone"
                    image={editImage}
                    onImage={setEditImage}
                    label="Drop or click to upload an image"
                    required
                  />
                </div>
              </div>
            </div>

            {/* Instruction */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <span className="font-semibold">Edit Instruction</span>
              </div>
              <div className="card-body">
                <div className="field-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="instruction-input">Describe the change</label>
                  <textarea
                    id="instruction-input"
                    placeholder="make the background a sunset beach · change the jacket to red · add dramatic studio lighting · replace the text with 'Hello World'…"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    style={{ minHeight: '110px' }}
                  />
                </div>

                {/* Edit-specific tips */}
                <div style={{ marginTop: '12px' }}>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Instruction tips
                  </p>
                  {[
                    'change the background to a foggy mountain forest',
                    'make the shirt blue',
                    'add dramatic rim lighting from the left',
                    'replace the sign text with "Open"',
                    'make it look like a vintage film photograph',
                  ].map((tip) => (
                    <code
                      key={tip}
                      className="font-mono"
                      onClick={() => setInstruction(tip)}
                      style={{ display: 'block', fontSize: '0.72rem', color: 'var(--accent2)', cursor: 'pointer', marginBottom: '4px' }}
                      title="Click to use"
                    >
                      {tip}
                    </code>
                  ))}
                </div>

                {/* Seed for edit */}
                <div className="field-group" style={{ marginTop: '16px', marginBottom: 0 }}>
                  <label htmlFor="edit-seed-input">Seed <span style={{ color: 'var(--text-muted)', textTransform: 'none', fontWeight: 400 }}>(-1 = random)</span></label>
                  <input type="number" id="edit-seed-input" value={seed} onChange={(e) => setSeed(e.target.value)} min={-1} placeholder="-1" />
                </div>
              </div>
            </div>
          </>
        )}

        {/* ── Shared: Enhancements ───────────────────────── */}
        <div className="card" style={{ marginBottom: '20px' }}>
          <div className="card-header">
            <span className="font-semibold">Pipeline Options</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label
              htmlFor="enhance-toggle"
              style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer', fontWeight: 400, textTransform: 'none' }}
            >
              <input
                type="checkbox"
                id="enhance-toggle"
                checked={enhancePrompt}
                onChange={(e) => setEnhancePrompt(e.target.checked)}
                style={{ marginTop: '2px', flexShrink: 0 }}
              />
              <span>
                <strong style={{ fontWeight: 600 }}>✨ Enhance prompt</strong>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.8rem' }}>
                  Qwen2.5-1.5B (local LLM on CPU) rewrites your prompt and auto-fills negatives before generating.
                </span>
              </span>
            </label>

            <label
              htmlFor="upscale-toggle"
              style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer', fontWeight: 400, textTransform: 'none' }}
            >
              <input
                type="checkbox"
                id="upscale-toggle"
                checked={upscale}
                onChange={(e) => setUpscale(e.target.checked)}
                style={{ marginTop: '2px', flexShrink: 0 }}
              />
              <span>
                <strong style={{ fontWeight: 600 }}>⬆ Upscale ×4 after generation</strong>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.8rem' }}>
                  RealESRGAN passes the output through a 4× super-resolution pass. Adds ~30s.
                </span>
              </span>
            </label>
          </div>
        </div>

        {/* ── Submit ─────────────────────────────────────── */}
        <button
          type="submit"
          id="generate-submit-btn"
          className={`btn btn-primary btn-lg btn-full ${isGenerating ? 'btn-loading' : ''}`}
          disabled={isGenerating || (topMode === 'generate' && modelsLoading)}
        >
          {isGenerating ? (
            <><span className="spinner" aria-hidden="true" /> Working…</>
          ) : topMode === 'generate' ? (
            '✦ Generate Image'
          ) : (
            '✎ Apply Edit'
          )}
        </button>
      </form>

      {/* ── Right: Output panel ─────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', position: 'sticky', top: '80px' }}>

        {/* Live stage+ETA progress */}
        {activeJobId && (
          <LiveProgress jobId={activeJobId} onDone={handleDone} />
        )}

        {/* Last output */}
        {lastOutput && !activeJobId && (
          <div className="card fade-in">
            <div className="card-header">
              <span className="font-semibold">{lastOutputMode === 'edit' ? 'Edited Image' : 'Output'}</span>
              <span className="badge badge-success">Done</span>
            </div>
            <div style={{ background: 'var(--bg-raised)' }}>
              <img
                src={lastOutput}
                alt={lastOutputMode === 'edit' ? 'Edited image' : 'Generated image'}
                style={{ width: '100%', display: 'block' }}
                id="output-image"
              />
            </div>
            <div className="card-body" style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <a
                href={lastOutput}
                download
                className="btn btn-secondary btn-sm"
                id="output-download-btn"
              >
                ↓ Download
              </a>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                id="output-edit-btn"
                title="Load this image into Edit mode"
                onClick={() => {
                  // Load output into edit mode
                  fetch(lastOutput)
                    .then((r) => r.blob())
                    .then((blob) => {
                      const reader = new FileReader();
                      reader.onload = (ev) => {
                        setEditImage(ev.target.result);
                        setTopMode('edit');
                      };
                      reader.readAsDataURL(blob);
                    })
                    .catch(() => toast.error('Could not load image for editing'));
                }}
              >
                ✎ Edit this
              </button>
            </div>
          </div>
        )}

        {/* Idle: prompt guide for generate, edit guide for edit */}
        {!activeJobId && !lastOutput && topMode === 'generate' && (
          <div className="card fade-in">
            <div className="card-body">
              <p className="text-sm" style={{ color: 'var(--text-muted)', marginBottom: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Prompt tips
              </p>
              {[
                ['Quality', 'masterpiece, best quality, 4k, ultra-detailed, sharp focus'],
                ['Style', 'cinematic, film grain, photorealistic, hyperrealistic'],
                ['Lighting', 'golden hour, dramatic rim lighting, volumetric light'],
                ['Composition', 'rule of thirds, shallow depth of field, bokeh'],
              ].map(([label, example]) => (
                <div key={label} style={{ marginBottom: '10px' }}>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{label}</p>
                  <code
                    className="font-mono"
                    style={{ fontSize: '0.72rem', color: 'var(--accent2)', cursor: 'pointer', display: 'block', marginTop: '2px' }}
                    onClick={() => setPrompt((p) => p ? `${p}, ${example}` : example)}
                    title="Click to append"
                  >
                    {example}
                  </code>
                </div>
              ))}
            </div>
          </div>
        )}

        {!activeJobId && !lastOutput && topMode === 'edit' && (
          <div className="card fade-in">
            <div className="card-body">
              <p className="text-sm" style={{ color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                How Edit works
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  ['Upload', 'Any image — photo, generate output, anything.'],
                  ['Instruct', 'Plain English: "make the background a forest", "change her jacket to red".'],
                  ['Kontext', 'FLUX.1 Kontext [dev] applies your instruction precisely, preserving everything else.'],
                  ['Enhance', 'Enable "Enhance prompt" to let Qwen refine your instruction before editing.'],
                ].map(([title, body]) => (
                  <div key={title}>
                    <p style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent)' }}>{title}</p>
                    <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '1px' }}>{body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
