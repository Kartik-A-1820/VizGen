/**
 * GalleryPage — browsable history of completed generations
 * Deliverables:
 *   ✓ Gallery / history view
 *   ✓ Download per item
 *   ✓ Lightbox
 *   ✓ Filter by mode
 *   ✓ Backed by Track B's /api/gallery endpoint
 * Track C — AGY
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchGallery, deleteGalleryItem, mediaUrl } from '../api.js';
import Lightbox from '../components/Lightbox.jsx';

const FILTERS = [
  { id: 'all',      label: 'All' },
  { id: 'generate', label: 'Generated' },
  { id: 'edit',     label: 'Edited' },
];

// Demo items shown when backend is offline
const DEMO_ITEMS = [
  {
    id: 'demo-1',
    prompt: 'a hyperrealistic portrait of a cyberpunk woman, neon lights, rain',
    model_id: 'z-image-turbo',
    mode: 'generate',
    width: 512, height: 512,
    steps: 12,
    output_url: null,
    created_at: new Date(Date.now() - 120000).toISOString(),
    _demo: true,
  },
  {
    id: 'demo-2',
    prompt: 'make the background a sunset beach',
    model_id: 'flux-kontext',
    mode: 'edit',
    width: 512, height: 512,
    steps: 20,
    output_url: null,
    created_at: new Date(Date.now() - 600000).toISOString(),
    _demo: true,
  },
];

function timeAgo(iso) {
  if (!iso) return '';
  const d = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export default function GalleryPage({ toast }) {
  const [items, setItems]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [page, setPage]         = useState(1);
  const [total, setTotal]       = useState(0);
  const [filter, setFilter]     = useState('all');
  const [lightbox, setLightbox] = useState(null);
  const [offline, setOffline]   = useState(false);
  const perPage = 24;

  const load = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const data = await fetchGallery({ page: p, per_page: perPage });
      const rawItems = Array.isArray(data) ? data : (data.items ?? []);
      const mappedItems = rawItems.map((item) => ({
        ...item,
        output_url: item.output_url ? mediaUrl(item.output_url) : null,
      }));
      setItems(p === 1 ? mappedItems : (prev) => [...prev, ...mappedItems]);
      setTotal(data.total ?? rawItems.length);
      setOffline(false);
    } catch {
      setOffline(true);
      if (p === 1) setItems(DEMO_ITEMS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(1); }, []);

  const handleDelete = useCallback(async (id) => {
    if (!window.confirm('Delete this item from history?')) return;
    try {
      await deleteGalleryItem(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      toast.success('Deleted');
    } catch (err) {
      toast.error(`Delete failed: ${err.message}`);
    }
  }, []);

  const filteredItems = filter === 'all' ? items : items.filter((i) => i.mode === filter);

  const isVideo = () => false;  // image-only after pivot

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
          Gallery
          {total > 0 && <span className="badge badge-muted" style={{ marginLeft: '12px', fontSize: '0.75rem' }}>{total} items</span>}
        </h1>

        {offline && (
          <span className="badge badge-warning">⚠ Backend offline — showing demo</span>
        )}

        {/* Filter pills */}
        <div className="mode-switch" role="group" aria-label="Filter by mode">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              id={`gallery-filter-${f.id}`}
              className={`mode-btn ${filter === f.id ? 'active' : ''}`}
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {loading && items.length === 0 && (
        <div className="empty-state">
          <div className="spinner" style={{ width: 28, height: 28 }} aria-label="Loading gallery" />
          <p>Loading gallery…</p>
        </div>
      )}

      {!loading && filteredItems.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🖼</div>
          <p className="empty-state-title">Nothing here yet</p>
          <p className="empty-state-desc">
            {filter !== 'all'
              ? `No ${filter} outputs yet. Try a different filter.`
              : 'Generate or edit your first image to see it here.'}
          </p>
        </div>
      )}

      {filteredItems.length > 0 && (
        <>
          <div className="output-grid">
            {filteredItems.map((item) => (
              <GalleryCard
                key={item.id}
                item={item}
                isVideo={isVideo(item)}
                onOpen={() => setLightbox(item)}
                onDelete={() => handleDelete(item.id)}
              />
            ))}
          </div>

          {/* Load more */}
          {!offline && items.length < total && (
            <div style={{ textAlign: 'center', marginTop: '32px' }}>
              <button
                className="btn btn-secondary"
                id="gallery-load-more-btn"
                onClick={() => { const next = page + 1; setPage(next); load(next); }}
                disabled={loading}
              >
                {loading ? <><span className="spinner" aria-hidden="true" /> Loading…</> : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}

      {/* Lightbox */}
      {lightbox && (
        <Lightbox
          item={lightbox}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

/* ── Gallery card sub-component ─────────────────── */
function GalleryCard({ item, isVideo, onOpen, onDelete }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="output-card"
      id={`gallery-item-${item.id}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role="article"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onOpen()}
    >
      {/* Thumbnail */}
      <div
        style={{ position: 'relative', cursor: 'pointer' }}
        onClick={onOpen}
        role="button"
        aria-label={`View: ${item.prompt}`}
      >
        {item.output_url ? (
          isVideo ? (
            <video
              src={item.output_url}
              className="output-card-media video-thumb"
              muted
              loop
              playsInline
              autoPlay={hovered}
            />
          ) : (
            <img
              className="output-card-media"
              src={item.output_url}
              alt={item.prompt}
              loading="lazy"
            />
          )
        ) : (
          /* Placeholder for demo items */
          <div
            className="output-card-media"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: '8px',
              background: `linear-gradient(135deg, var(--bg-raised), var(--accent-dim))`,
            }}
          >
            <span style={{ fontSize: '2rem', opacity: 0.4 }}>🖼</span>
            <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Demo item</span>
          </div>
        )}

        {/* Mode badge overlay */}
        <span
          className={`badge ${item.mode === 'edit' ? 'badge-info' : 'badge-accent'}`}
          style={{ position: 'absolute', top: 8, left: 8 }}
        >
          {item.mode === 'edit' ? 'EDIT' : 'GEN'}
        </span>

        {/* Hover overlay */}
        {hovered && (
          <div
            style={{
              position: 'absolute', inset: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '1.5rem',
            }}
            aria-hidden="true"
          >
            🔍
          </div>
        )}
      </div>

      {/* Info */}
      <div className="output-card-info">
        <p className="output-card-prompt" title={item.prompt}>{item.prompt || '—'}</p>
        <div className="output-card-meta">
          <span className="text-sm text-muted">{timeAgo(item.created_at)}</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            {item.output_url && (
              <a
                href={item.output_url}
                download
                className="btn btn-ghost btn-sm"
                id={`gallery-download-${item.id}`}
                onClick={(e) => e.stopPropagation()}
                aria-label="Download"
                title="Download"
              >
                ↓
              </a>
            )}
            <button
              className="btn btn-ghost btn-sm"
              id={`gallery-delete-${item.id}`}
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              aria-label="Delete"
              title="Delete from history"
              style={{ color: 'var(--error)' }}
            >
              ✕
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
