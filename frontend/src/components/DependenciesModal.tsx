import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';

interface Props {
  open: boolean;
  onClose: () => void;
}

interface LogLine {
  message: string;
  isError?: boolean;
}

export default function DependenciesModal({ open, onClose }: Props) {
  const [packages, setPackages] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [log, setLog] = useState<LogLine[]>([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const fetchPackages = useCallback(async () => {
    try {
      const res = await api.get('/dependencies');
      setPackages(res.data.packages ?? []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchPackages();
      setLog([]);
    }
  }, [open, fetchPackages]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  const streamPip = async (url: string, pkgs: string[]) => {
    setBusy(true);
    setLog([]);
    try {
      const response = await fetch(`http://localhost:8000${url}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packages: pkgs }),
      });
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'log') {
                setLog((prev) => [...prev, { message: event.message }]);
              } else if (event.type === 'done') {
                if (event.status === 'ok') {
                  setLog((prev) => [...prev, { message: 'Done.' }]);
                } else {
                  setLog((prev) => [...prev, { message: `Error: ${event.message}`, isError: true }]);
                }
              }
            } catch {
              // skip
            }
          }
        }
      }
    } catch (err: any) {
      setLog((prev) => [...prev, { message: `Network error: ${err.message}`, isError: true }]);
    } finally {
      setBusy(false);
      fetchPackages();
    }
  };

  const handleInstall = () => {
    const pkgs = input
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (pkgs.length === 0) return;
    setInput('');
    streamPip('/api/dependencies/install', pkgs);
  };

  const handleUninstall = (pkg: string) => {
    streamPip('/api/dependencies/uninstall', [pkg]);
  };

  if (!open) return null;

  return (
    <div className="deps-overlay" onClick={onClose}>
      <div className="deps-modal" onClick={(e) => e.stopPropagation()}>
        <div className="deps-header">
          <h3>Python Dependencies</h3>
          <button className="deps-close" onClick={onClose}>&times;</button>
        </div>

        {/* Install bar */}
        <div className="deps-install-bar">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !busy && handleInstall()}
            placeholder="e.g. pandas>=2.0, scikit-learn"
            disabled={busy}
            spellCheck={false}
          />
          <button onClick={handleInstall} disabled={busy || !input.trim()}>
            {busy ? 'Installing...' : 'Install'}
          </button>
        </div>

        {/* Log output */}
        {log.length > 0 && (
          <div className="deps-log" ref={logRef}>
            {log.map((l, i) => (
              <div key={i} className={l.isError ? 'deps-log-error' : ''}>
                {l.message}
              </div>
            ))}
          </div>
        )}

        {/* Installed packages */}
        <div className="deps-list">
          <div className="deps-list-header">Installed packages</div>
          {packages.length === 0 ? (
            <div className="deps-list-empty">No custom packages installed</div>
          ) : (
            packages.map((pkg) => (
              <div key={pkg} className="deps-list-item">
                <span className="deps-pkg-name">{pkg}</span>
                <button
                  className="deps-remove-btn"
                  onClick={() => handleUninstall(pkg)}
                  disabled={busy}
                  title="Uninstall"
                >
                  &times;
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
