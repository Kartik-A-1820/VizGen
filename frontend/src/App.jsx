/**
 * App.jsx — root component / router (post-pivot: image + edit only)
 * Track C — AGY
 */
import React, { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ToastContainer from './components/ToastContainer.jsx';
import { useToast } from './hooks/useToast.js';
import GeneratePage from './pages/GeneratePage.jsx';
import QueuePage from './pages/QueuePage.jsx';
import GalleryPage from './pages/GalleryPage.jsx';
import './index.css';

const PAGE_TITLES = {
  generate: 'Generate & Edit',
  queue:    'Job Queue',
  gallery:  'Gallery',
};

export default function App() {
  const [page, setPage]             = useState('generate');
  const [queueCount, setQueueCount] = useState(0);
  const toast = useToast();

  const handleJobSubmitted = useCallback(() => {
    setQueueCount((n) => n + 1);
  }, []);

  return (
    <div className="app-shell">
      <Sidebar page={page} onNav={setPage} queueCount={queueCount} />

      <main className="main-content" id="main-content">
        <header className="page-header">
          <h2 className="page-title">{PAGE_TITLES[page] ?? page}</h2>
          <span className="text-sm" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            local · no cloud · no filters
          </span>
        </header>

        <div className="page-body">
          {page === 'generate' && (
            <GeneratePage onJobSubmitted={handleJobSubmitted} toast={toast} />
          )}
          {page === 'queue' && <QueuePage toast={toast} />}
          {page === 'gallery' && <GalleryPage toast={toast} />}
        </div>
      </main>

      <ToastContainer toasts={toast.toasts} dismiss={toast.dismiss} />
    </div>
  );
}
