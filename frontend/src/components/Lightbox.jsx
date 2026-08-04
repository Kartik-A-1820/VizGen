/**
 * Lightbox — full-screen media viewer
 * Track C — AGY
 */
import React, { useEffect, useCallback } from 'react';

export default function Lightbox({ item, onClose }) {
  const isVideo = item?.type === 'video' || item?.output_url?.match(/\.(mp4|webm|mov)$/i);

  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  if (!item) return null;

  return (
    <div
      className="lightbox-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
    >
      <div
        className="lightbox-content"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="lightbox-close"
          onClick={onClose}
          aria-label="Close viewer"
          id="lightbox-close-btn"
        >
          ✕
        </button>

        {isVideo ? (
          <video
            src={item.output_url}
            controls
            autoPlay
            loop
            playsInline
            style={{ maxWidth: '100%', maxHeight: '80vh', borderRadius: 'var(--radius-lg)' }}
          />
        ) : (
          <img
            src={item.output_url}
            alt={item.prompt || 'Generated image'}
            loading="eager"
          />
        )}

        {/* Metadata strip */}
        <div
          className="glass"
          style={{
            marginTop: '12px',
            padding: '12px 16px',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '16px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: '4px' }}>
              {item.prompt}
            </p>
            {item.negative && (
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                ✗ {item.negative}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-end', flexShrink: 0 }}>
            {item.model_id && (
              <span className="badge badge-accent">{item.model_id}</span>
            )}
            {item.width && item.height && (
              <span className="badge badge-muted">{item.width}×{item.height}</span>
            )}
            {item.steps && (
              <span className="badge badge-muted">{item.steps} steps</span>
            )}
          </div>
        </div>

        {/* Download */}
        <div style={{ marginTop: '8px', textAlign: 'right' }}>
          <a
            href={item.output_url}
            download
            className="btn btn-secondary btn-sm"
            id="lightbox-download-btn"
            onClick={(e) => e.stopPropagation()}
          >
            ↓ Download
          </a>
        </div>
      </div>
    </div>
  );
}
