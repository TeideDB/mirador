import { useCallback, useEffect, useRef, useState } from 'react';
import useStore, { type AppView } from '../store/useStore';
import { IconTeide } from './icons';

const VERSION = '0.1.0';
const GITHUB_URL = 'https://github.com/akundenko/teide';

const tabs: { view: AppView; label: string }[] = [
  { view: 'workflows', label: 'Pipelines' },
  { view: 'dashboards', label: 'Dashboards' },
];

/** Map editor views to their parent list tab for active highlighting */
function activeTab(view: AppView): AppView {
  if (view === 'workflow-editor') return 'workflows';
  if (view === 'dashboard-editor') return 'dashboards';
  return view;
}

export default function NavBar() {
  const currentView = useStore((s) => s.currentView);
  const setView = useStore((s) => s.setView);
  const currentWorkflowName = useStore((s) => s.currentWorkflowName);
  const currentDashboardName = useStore((s) => s.currentDashboardName);
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const active = activeTab(currentView);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  // Cmd/Ctrl+K shortcut to open search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setSearchOpen(false);
        setSearchQuery('');
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  // Focus search input when opened
  useEffect(() => {
    if (searchOpen) {
      requestAnimationFrame(() => searchInputRef.current?.focus());
    }
  }, [searchOpen]);

  const navigate = useCallback((view: AppView) => {
    setView(view);
    setMenuOpen(false);
  }, [setView]);

  return (
    <nav className="navbar">
      {/* Logo dropdown menu */}
      <div className="navbar-brand-menu" ref={menuRef}>
        <button className="navbar-brand-btn" onClick={() => setMenuOpen(!menuOpen)}>
          <IconTeide />
          <span className="navbar-title">Mirador</span>
          <svg className="navbar-chevron" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 4 L5 6.5 L7.5 4"/>
          </svg>
        </button>
        {menuOpen && (
          <div className="navbar-dropdown">
            <button className="navbar-dropdown-item" onClick={() => navigate('workflows')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1"/>
                <rect x="14" y="3" width="7" height="7" rx="1"/>
                <rect x="3" y="14" width="7" height="7" rx="1"/>
                <path d="M17.5 14v7M14 17.5h7"/>
              </svg>
              Pipelines
            </button>
            <button className="navbar-dropdown-item" onClick={() => navigate('dashboards')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <path d="M3 9h18M9 21V9"/>
              </svg>
              Dashboards
            </button>
            <div className="navbar-dropdown-sep" />
            <a className="navbar-dropdown-item" href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              {/* GitHub icon */}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              GitHub
            </a>
            <div className="navbar-dropdown-sep" />
            <div className="navbar-dropdown-version">
              v{VERSION}
            </div>
          </div>
        )}
      </div>

      {/* Navigation tabs — always visible */}
      <div className="navbar-tabs">
        {tabs.map((t) => (
          <button
            key={t.view}
            className={`navbar-tab${active === t.view ? ' active' : ''}`}
            onClick={() => setView(t.view)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Breadcrumb for current editor context */}
      {currentView === 'workflow-editor' && currentWorkflowName && (
        <div className="navbar-breadcrumb">
          <span className="navbar-breadcrumb-sep">/</span>
          <span className="navbar-breadcrumb-name">{currentWorkflowName}</span>
        </div>
      )}
      {currentView === 'dashboard-editor' && currentDashboardName && (
        <div className="navbar-breadcrumb">
          <span className="navbar-breadcrumb-sep">/</span>
          <span className="navbar-breadcrumb-name">{currentDashboardName}</span>
        </div>
      )}

      <div className="navbar-spacer" />

      {/* Global search — styled as a wide input-like trigger */}
      <div className="navbar-search-trigger" onClick={() => setSearchOpen(true)} role="button" tabIndex={0}>
        <svg className="navbar-search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7"/>
          <path d="M21 21l-4.35-4.35"/>
        </svg>
        <span className="navbar-search-placeholder">Search...</span>
        <kbd className="navbar-search-kbd">{navigator.platform?.includes('Mac') ? '\u2318K' : 'Ctrl+K'}</kbd>
      </div>

      {/* GitHub icon */}
      <a className="navbar-github-icon" href={GITHUB_URL} target="_blank" rel="noopener noreferrer" title="View on GitHub">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
        </svg>
      </a>

      {/* Search overlay */}
      {searchOpen && (
        <div className="navbar-search-overlay" onClick={() => { setSearchOpen(false); setSearchQuery(''); }}>
          <div className="navbar-search-modal" onClick={(e) => e.stopPropagation()}>
            <div className="navbar-search-input-row">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search pipelines, dashboards, nodes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <kbd className="navbar-search-kbd">Esc</kbd>
            </div>
            <div className="navbar-search-results">
              {searchQuery.trim() === '' ? (
                <div className="navbar-search-empty">Start typing to search...</div>
              ) : (
                <div className="navbar-search-empty">No results for "{searchQuery}"</div>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
