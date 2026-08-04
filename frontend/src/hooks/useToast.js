/**
 * useToast — lightweight toast notification system
 * Track C — AGY
 */
import { useState, useCallback } from 'react';

let _nextId = 0;

export function useToast() {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const show = useCallback((message, { type = 'info', duration = 4000 } = {}) => {
    const id = ++_nextId;
    setToasts((t) => [...t, { id, message, type }]);
    if (duration > 0) setTimeout(() => dismiss(id), duration);
    return id;
  }, [dismiss]);

  const success = useCallback((msg, opts) => show(msg, { type: 'success', ...opts }), [show]);
  const error   = useCallback((msg, opts) => show(msg, { type: 'error',   ...opts }), [show]);
  const info    = useCallback((msg, opts) => show(msg, { type: 'info',    ...opts }), [show]);

  return { toasts, show, success, error, info, dismiss };
}
