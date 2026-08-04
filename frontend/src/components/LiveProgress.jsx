/**
 * LiveProgress — WebSocket-driven generation progress card
 * Track C — AGY
 */
import React, { useState, useEffect, useRef } from 'react';
import { openJobSocket, mediaUrl } from '../api.js';

const STAGE_LABELS = {
  enhance:  'Enhancing prompt',
  generate: 'Generating image',
  edit:     'Editing image',
  upscale:  'Upscaling ×4',
  done:     'Complete',
  failed:   'Failed',
};

function fmtEta(sec) {
  if (!sec || sec <= 0) return '';
  const s = Math.round(sec);
  if (s < 60) return `~${s}s left`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `~${m}m${r ? ` ${r}s` : ''} left`;
}

export default function LiveProgress({ jobId, onDone }) {
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');
  const [stageIndex, setStageIndex] = useState(0);
  const [stageTotal, setStageTotal] = useState(1);
  const [message, setMessage] = useState('');
  const [eta, setEta] = useState(0);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [error, setError] = useState(null);
  const closeRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;

    setProgress(0);
    setStage('');
    setStageIndex(0);
    setStageTotal(1);
    setMessage('');
    setEta(0);
    setPreviewUrl(null);
    setError(null);

    closeRef.current = openJobSocket(jobId, {
      onProgress: (data) => {
        setProgress(data.progress ?? 0);
        setStage(data.stage ?? '');
        setStageIndex(data.stage_index ?? 0);
        setStageTotal(data.stage_total ?? 1);
        setMessage(data.message ?? '');
        setEta(data.eta_seconds ?? 0);
        if (data.preview_url) setPreviewUrl(mediaUrl(data.preview_url));
      },
      onDone: (data) => {
        setProgress(100);
        onDone?.(data);
      },
      onError: (msg) => {
        setError(msg);
      },
    });

    return () => closeRef.current?.();
  }, [jobId]);

  if (!jobId) return null;

  const stageLabel = STAGE_LABELS[stage] || 'Working';

  return (
    <div className="live-progress-card fade-in" role="status" aria-label="Generation progress">
      <div className="live-progress-title">
        <span className="live-dot" aria-hidden="true" />
        {stageLabel}
        {stageTotal > 1 ? ` (step ${stageIndex}/${stageTotal})` : ''}
        {eta ? <span style={{ marginLeft: 'auto', fontWeight: 400, opacity: 0.7, fontSize: '0.85rem' }}>{fmtEta(eta)}</span> : null}
      </div>
      {message ? (
        <div style={{ fontSize: '0.8rem', opacity: 0.8, marginBottom: '8px' }}>{message}</div>
      ) : null}

      {error ? (
        <p style={{ color: 'var(--error)', fontSize: '0.875rem' }}>⚠ {error}</p>
      ) : (
        <>
          <div className="progress-bar" style={{ marginBottom: '12px' }}>
            <div
              className={`progress-bar-fill ${progress === 0 ? 'progress-bar-indeterminate' : ''}`}
              style={{ width: `${progress}%` }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
            {previewUrl && (
              <img
                src={previewUrl}
                alt="Live generation preview"
                style={{
                  width: 120, height: 72,
                  objectFit: 'cover',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-default)',
                }}
              />
            )}
            <span
              className="font-mono"
              style={{ color: 'var(--accent)', fontSize: '1.5rem', fontWeight: 700, marginLeft: 'auto' }}
              aria-label={`${Math.round(progress)} percent complete`}
            >
              {Math.round(progress)}%
            </span>
          </div>
        </>
      )}
    </div>
  );
}
