/**
 * Sidebar — navigation panel
 * Track C — AGY
 */
import React from 'react';

const NAV_ITEMS = [
  { id: 'generate', icon: '✦', label: 'Generate & Edit' },
  { id: 'queue',    icon: '⟳', label: 'Queue' },
  { id: 'gallery',  icon: '◫', label: 'Gallery' },
];

export default function Sidebar({ page, onNav, queueCount = 0 }) {
  return (
    <aside className="sidebar" role="navigation" aria-label="Main navigation">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon" aria-hidden="true">⚡</div>
        <span className="sidebar-logo-text">ImageGen</span>
      </div>

      {/* Nav links */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            id={`nav-${item.id}`}
            className={`nav-item ${page === item.id ? 'active' : ''}`}
            onClick={() => onNav(item.id)}
            aria-current={page === item.id ? 'page' : undefined}
          >
            <span className="nav-icon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
            {item.id === 'queue' && queueCount > 0 && (
              <span
                className="badge badge-accent"
                style={{ marginLeft: 'auto', minWidth: '22px', justifyContent: 'center' }}
                aria-label={`${queueCount} jobs in queue`}
              >
                {queueCount}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer — GPU status */}
      <div className="sidebar-footer">
        <div className="gpu-badge">
          <span className="gpu-dot" aria-hidden="true" />
          <span>GTX 1650 Ti · 4GB</span>
        </div>
      </div>
    </aside>
  );
}
