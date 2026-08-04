/**
 * QueuePage — live job queue view
 * Deliverables:
 *   ✓ Queue position for each job
 *   ✓ Live updates via WebSocket
 *   ✓ Cancel queued jobs
 * Track C — AGY
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { fetchQueue, cancelJob, openQueueSocket } from '../api.js';

const STATUS_BADGE = {
  queued:  { cls: 'badge-muted',   label: 'Queued' },
  running: { cls: 'badge-accent',  label: '⚡ Running' },
  done:    { cls: 'badge-success', label: 'Done' },
  failed:  { cls: 'badge-error',   label: 'Failed' },
};

function timeAgo(isoString) {
  if (!isoString) return '';
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (diff < 60)  return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function QueuePage({ toast }) {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const closeRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchQueue();
      setQueue(Array.isArray(data) ? data : []);
    } catch {
      // backend offline — show empty
      setQueue([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // WebSocket live updates
    closeRef.current = openQueueSocket({
      onUpdate: (snapshot) => {
        setQueue(Array.isArray(snapshot) ? snapshot : []);
      },
    });
    return () => closeRef.current?.();
  }, []);

  const handleCancel = useCallback(async (jobId) => {
    try {
      await cancelJob(jobId);
      setQueue((q) => q.filter((j) => j.job_id !== jobId));
      toast.success('Job cancelled');
    } catch (err) {
      toast.error(`Cancel failed: ${err.message}`);
    }
  }, []);

  const running = queue.filter((j) => j.status === 'running');
  const pending = queue.filter((j) => j.status === 'queued');

  return (
    <div style={{ maxWidth: 800 }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '24px', letterSpacing: '-0.02em' }}>
        Job Queue
      </h1>

      {/* Summary */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        {[
          { label: 'Running',  value: running.length, cls: 'badge-accent' },
          { label: 'Waiting',  value: pending.length, cls: 'badge-muted' },
          { label: 'Total',    value: queue.length,   cls: 'badge-info' },
        ].map(({ label, value, cls }) => (
          <div key={label} className="card glass">
            <div className="card-body" style={{ textAlign: 'center', padding: '20px' }}>
              <p style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>{value}</p>
              <p className="text-sm" style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
                <span className={`badge ${cls}`}>{label}</span>
              </p>
            </div>
          </div>
        ))}
      </div>

      {loading && (
        <div className="empty-state">
          <div className="spinner" style={{ width: 28, height: 28 }} aria-label="Loading" />
          <p>Loading queue…</p>
        </div>
      )}

      {!loading && queue.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🎯</div>
          <p className="empty-state-title">Queue is empty</p>
          <p className="empty-state-desc">Go to Generate to submit your first job.</p>
        </div>
      )}

      {!loading && queue.length > 0 && (
        <div className="queue-list" role="list">
          {queue.map((job, idx) => {
            const badge = STATUS_BADGE[job.status] ?? { cls: 'badge-muted', label: job.status };
            return (
              <div
                key={job.job_id}
                className="queue-item fade-in"
                role="listitem"
                id={`queue-item-${job.job_id}`}
              >
                {/* Position */}
                <div className="queue-item-num" aria-label={`Position ${idx + 1}`}>
                  {job.status === 'running' ? '⚡' : idx + 1}
                </div>

                {/* Info */}
                <div className="queue-item-info">
                  <div className="queue-item-prompt" title={job.prompt}>
                    {job.prompt || '(no prompt)'}
                  </div>
                  <div className="queue-item-meta">
                    {job.model_id && <span>{job.model_id}</span>}
                    {job.mode && <span className="badge badge-muted" style={{ padding: '1px 6px' }}>{job.mode.toUpperCase()}</span>}
                    {job.submitted_at && <span>{timeAgo(job.submitted_at)}</span>}
                  </div>

                  {/* Progress bar for running job */}
                  {job.status === 'running' && (
                    <div style={{ marginTop: '8px' }}>
                      <div className={`progress-bar ${job.progress == null ? 'progress-bar-indeterminate' : ''}`}>
                        <div
                          className="progress-bar-fill"
                          style={{ width: `${job.progress ?? 0}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Status badge */}
                <span className={`badge ${badge.cls}`}>{badge.label}</span>

                {/* Cancel button — only for queued jobs */}
                {job.status === 'queued' && (
                  <button
                    className="btn btn-danger btn-sm"
                    id={`cancel-job-${job.job_id}`}
                    onClick={() => handleCancel(job.job_id)}
                    aria-label={`Cancel job ${job.job_id}`}
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
