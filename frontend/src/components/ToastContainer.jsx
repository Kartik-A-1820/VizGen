/**
 * ToastContainer — renders active toast notifications
 * Track C — AGY
 */
import React from 'react';

const ICONS = { success: '✓', error: '✕', info: 'ℹ' };

export default function ToastContainer({ toasts, dismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-container" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast-${t.type}`}
          onClick={() => dismiss(t.id)}
          role="alert"
          style={{ cursor: 'pointer' }}
        >
          <span style={{ fontSize: '0.9rem' }}>{ICONS[t.type] ?? 'ℹ'}</span>
          <span style={{ flex: 1 }}>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
