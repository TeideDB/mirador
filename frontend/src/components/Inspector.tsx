import { useCallback, useMemo, useRef, useState } from 'react';
import { useReactFlow } from '@xyflow/react';
import useStore from '../store/useStore';
import { NodeIcon } from './icons';
import FileBrowser from './FileBrowser';
import CodeEditor from './CodeEditor';

export default function Inspector() {
  const inspectorNodeId = useStore((s) => s.inspectorNodeId);
  // Narrow selectors: only re-render when our specific node or its results change
  const node = useStore((s) => s.nodes.find((n) => n.id === s.inspectorNodeId));
  const edges = useStore((s) => s.edges);
  const updateNodeConfig = useStore((s) => s.updateNodeConfig);
  const updateNodeLabel = useStore((s) => s.updateNodeLabel);
  const setInspectorNodeId = useStore((s) => s.setInspectorNodeId);
  const nodeResults = useStore((s) => s.nodeResults);
  const { deleteElements } = useReactFlow();
  const [showFileBrowser, setShowFileBrowser] = useState(false);
  const [fileBrowserTarget, setFileBrowserTarget] = useState<string>('file_path');

  const setConfig = useCallback(
    (key: string, value: any) => {
      if (!inspectorNodeId) return;
      updateNodeConfig(inspectorNodeId, { [key]: value });
    },
    [inspectorNodeId, updateNodeConfig]
  );

  const onClose = useCallback(() => setInspectorNodeId(null), [setInspectorNodeId]);

  const onDelete = useCallback(() => {
    if (!inspectorNodeId) return;
    deleteElements({ nodes: [{ id: inspectorNodeId }] });
    setInspectorNodeId(null);
  }, [inspectorNodeId, deleteElements, setInspectorNodeId]);

  // Compute upstream columns from last run results
  const upstreamColumns = useMemo(() => {
    if (!inspectorNodeId) return [];
    const parentEdge = edges.find((e) => e.target === inspectorNodeId);
    if (!parentEdge) return [];
    const parentResult = nodeResults[parentEdge.source];
    if (parentResult?.columns) return parentResult.columns as string[];
    return [];
  }, [inspectorNodeId, edges, nodeResults]);

  if (!node) return null;

  const { nodeType, label, category, config } = node.data;

  return (
    <div className="inspector-overlay" onClick={onClose} onMouseDown={(e) => e.stopPropagation()}>
      <div className="inspector-modal" onClick={(e) => e.stopPropagation()}>
        <div className="inspector-header">
          <div className="inspector-title">
            <div className="inspector-icon">
              <NodeIcon nodeType={nodeType} size={20} />
            </div>
            <input
              className="inspector-name-input"
              value={label}
              onChange={(e) => {
                if (inspectorNodeId) updateNodeLabel(inspectorNodeId, e.target.value);
              }}
              spellCheck={false}
            />
            <span className={`inspector-badge cat-${category}`}>{category}</span>
          </div>
          <div className="inspector-actions">
            <button className="inspector-delete-btn" onClick={onDelete} title="Delete node">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
                <path d="M3 4h8M5 4V3a1 1 0 011-1h2a1 1 0 011 1v1M4.5 4v7a1 1 0 001 1h3a1 1 0 001-1V4"/>
              </svg>
            </button>
            <button className="inspector-close-btn" onClick={onClose} title="Close">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M3 3l8 8M11 3l-8 8"/>
              </svg>
            </button>
          </div>
        </div>

        <div className="inspector-body">
          {/* file_path — text input with browse button */}
          {nodeType === 'csv_source' && (
            <div className="field-group">
              <label>File Path</label>
              <div className="file-input-row">
                <input
                  type="text"
                  value={config.file_path ?? ''}
                  onChange={(e) => setConfig('file_path', e.target.value)}
                  placeholder="/path/to/data.csv"
                />
                <button
                  className="browse-btn"
                  onClick={() => {
                    setFileBrowserTarget('file_path');
                    setShowFileBrowser(true);
                  }}
                  title="Browse files"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M1 3.5C1 2.67 1.67 2 2.5 2H6l1.5 1.5H13.5C14.33 3.5 15 4.17 15 5V12.5C15 13.33 14.33 14 13.5 14H2.5C1.67 14 1 13.33 1 12.5V3.5Z" fill="currentColor" opacity="0.7"/>
                  </svg>
                </button>
              </div>
              {showFileBrowser && fileBrowserTarget === 'file_path' && (
                <FileBrowser
                  onSelect={(path) => {
                    setConfig('file_path', path);
                    setShowFileBrowser(false);
                  }}
                  onClose={() => setShowFileBrowser(false)}
                />
              )}
            </div>
          )}

          {/* Query node — form + SQL toggle */}
          {nodeType === 'query' && (
            <QueryInspector config={config} setConfig={setConfig}
              showFileBrowser={showFileBrowser}
              setShowFileBrowser={setShowFileBrowser}
              fileBrowserTarget={fileBrowserTarget}
              setFileBrowserTarget={setFileBrowserTarget}
              upstreamColumns={upstreamColumns}
            />
          )}

          {/* Formula node — expression + output column */}
          {nodeType === 'formula' && (
            <>
              <div className="field-group">
                <label>Output Column</label>
                <input
                  type="text"
                  value={config.output_column ?? ''}
                  onChange={(e) => setConfig('output_column', e.target.value)}
                  placeholder="result"
                />
              </div>
              <div className="field-group">
                <label>Expression</label>
                <CodeEditor
                  value={config.expression ?? ''}
                  onChange={(val) => setConfig('expression', val)}
                  language="python"
                  placeholder="col1 + col2 * 0.1"
                  minHeight="100px"
                />
              </div>
              {upstreamColumns.length > 0 && (
                <div className="field-group">
                  <label>Available Columns</label>
                  <div className="sql-columns">
                    {upstreamColumns.map((col) => (
                      <span key={col} className="sql-col-pill">{col}</span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Script node — Python code editor */}
          {nodeType === 'script' && (
            <div className="field-group">
              <label>Python Code</label>
              <CodeEditor
                value={config.code ?? ''}
                onChange={(val) => setConfig('code', val)}
                language="python"
                placeholder="# df is a list of dicts&#10;result = [r for r in df if r[&quot;value&quot;] > 0]"
                minHeight="240px"
              />
            </div>
          )}

          {/* Grid (output) fields */}
          {nodeType === 'grid' && (
            <div className="field-group">
              <label>Page Size</label>
              <input
                type="number"
                value={config.page_size ?? 100}
                onChange={(e) => setConfig('page_size', parseInt(e.target.value) || 100)}
                min={1}
                max={10000}
              />
            </div>
          )}

          {/* Schedule Trigger fields */}
          {nodeType === 'schedule_trigger' && (
            <ScheduleTriggerInspector config={config} setConfig={setConfig} />
          )}

          {/* HTTP Request fields */}
          {nodeType === 'http_request' && (
            <HttpRequestInspector config={config} setConfig={setConfig} />
          )}

          {/* PDF Render fields */}
          {nodeType === 'pdf_render' && (
            <PdfRenderInspector config={config} setConfig={setConfig} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- Schedule Trigger inspector sub-component ---------- */

const CRON_PRESETS = [
  { label: 'Every 5 min', cron: '*/5 * * * *' },
  { label: 'Every 15 min', cron: '*/15 * * * *' },
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Daily 9 AM', cron: '0 9 * * *' },
  { label: 'Daily midnight', cron: '0 0 * * *' },
  { label: 'Weekly Monday', cron: '0 9 * * 1' },
];

function ScheduleTriggerInspector({
  config,
  setConfig,
}: {
  config: Record<string, any>;
  setConfig: (key: string, value: any) => void;
}) {
  return (
    <>
      <div className="field-group">
        <label>Cron Expression</label>
        <input
          type="text"
          value={config.cron_expression ?? ''}
          onChange={(e) => setConfig('cron_expression', e.target.value)}
          placeholder="*/5 * * * *"
          spellCheck={false}
          style={{ fontFamily: 'var(--font-mono, monospace)' }}
        />
      </div>
      <div className="field-group">
        <label>Presets</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {CRON_PRESETS.map((p) => (
            <button
              key={p.cron}
              className="sql-template-btn"
              onClick={() => setConfig('cron_expression', p.cron)}
              style={{ fontSize: 11 }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="field-group">
        <label>Timezone</label>
        <input
          type="text"
          value={config.timezone ?? 'UTC'}
          onChange={(e) => setConfig('timezone', e.target.value)}
          placeholder="UTC"
        />
      </div>
      <div className="field-group">
        <div className="checkbox-row">
          <input
            type="checkbox"
            checked={config.enabled ?? true}
            onChange={(e) => setConfig('enabled', e.target.checked)}
          />
          <span>Enabled</span>
        </div>
      </div>
    </>
  );
}

/* ---------- HTTP Request inspector sub-component ---------- */

interface HeaderRow { key: string; value: string }

function HttpRequestInspector({
  config,
  setConfig,
}: {
  config: Record<string, any>;
  setConfig: (key: string, value: any) => void;
}) {
  const mode = config.mode ?? 'fetch';
  const method = config.method ?? 'GET';
  const headers: HeaderRow[] = config.headers ?? [];

  const [showHeaders, setShowHeaders] = useState(false);

  const updateHeader = (idx: number, field: keyof HeaderRow, val: string) => {
    const next = [...headers];
    next[idx] = { ...next[idx], [field]: val };
    setConfig('headers', next);
  };

  const addHeader = () => setConfig('headers', [...headers, { key: '', value: '' }]);

  const removeHeader = (idx: number) => {
    setConfig('headers', headers.filter((_, i) => i !== idx));
  };

  return (
    <>
      {/* Mode toggle */}
      <div className="query-mode-toggle">
        <button className={mode === 'fetch' ? 'active' : ''} onClick={() => setConfig('mode', 'fetch')}>
          Fetch
        </button>
        <button className={mode === 'send' ? 'active' : ''} onClick={() => setConfig('mode', 'send')}>
          Send
        </button>
      </div>

      <div className="field-group">
        <label>URL</label>
        <input
          type="text"
          value={config.url ?? ''}
          onChange={(e) => setConfig('url', e.target.value)}
          placeholder="https://api.example.com/data"
          spellCheck={false}
        />
      </div>

      <div className="field-group">
        <label>Method</label>
        <select value={method} onChange={(e) => setConfig('method', e.target.value)}>
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="DELETE">DELETE</option>
        </select>
      </div>

      {/* Headers (collapsible) */}
      <div className="query-section">
        <div className="query-section-header" onClick={() => setShowHeaders(!showHeaders)}>
          <span className="query-section-chevron">{showHeaders ? '\u25BE' : '\u25B8'}</span>
          <span>Headers</span>
          {headers.length > 0 && <span className="query-section-active">&bull;</span>}
        </div>
        {showHeaders && (
          <div className="query-section-body">
            {headers.map((h, i) => (
              <div className="array-item" key={i}>
                <input
                  type="text"
                  value={h.key}
                  onChange={(e) => updateHeader(i, 'key', e.target.value)}
                  placeholder="Header name"
                  style={{ flex: 1 }}
                />
                <input
                  type="text"
                  value={h.value}
                  onChange={(e) => updateHeader(i, 'value', e.target.value)}
                  placeholder="Value"
                  style={{ flex: 1 }}
                />
                <button className="remove-btn" onClick={() => removeHeader(i)}>&times;</button>
              </div>
            ))}
            <button className="add-btn" onClick={addHeader}>+ Add header</button>
          </div>
        )}
      </div>

      {/* Body (fetch mode, POST/PUT) */}
      {mode === 'fetch' && (method === 'POST' || method === 'PUT') && (
        <div className="field-group">
          <label>Request Body</label>
          <CodeEditor
            value={config.body ?? ''}
            onChange={(val) => setConfig('body', val)}
            language="json"
            placeholder='{"key": "value"}'
            minHeight="80px"
          />
        </div>
      )}

      {/* JSON Path (fetch mode) */}
      {mode === 'fetch' && (
        <div className="field-group">
          <label>JSON Path</label>
          <input
            type="text"
            value={config.json_path ?? ''}
            onChange={(e) => setConfig('json_path', e.target.value)}
            placeholder="data.results"
            spellCheck={false}
            style={{ fontFamily: 'var(--font-mono, monospace)' }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            Dot-notation path to extract from response JSON
          </span>
        </div>
      )}

      <div className="field-group">
        <label>Timeout (seconds)</label>
        <input
          type="number"
          value={config.timeout ?? 30}
          onChange={(e) => setConfig('timeout', parseInt(e.target.value) || 30)}
          min={1}
          max={300}
        />
      </div>
    </>
  );
}

/* ---------- Query inspector sub-component ---------- */

function QueryInspector({
  config,
  setConfig,
  showFileBrowser,
  setShowFileBrowser,
  fileBrowserTarget,
  setFileBrowserTarget,
  upstreamColumns,
}: {
  config: Record<string, any>;
  setConfig: (key: string, value: any) => void;
  showFileBrowser: boolean;
  setShowFileBrowser: (v: boolean) => void;
  fileBrowserTarget: string;
  setFileBrowserTarget: (v: string) => void;
  upstreamColumns: string[];
}) {
  const mode = config.mode ?? 'form';
  const sqlInsertRef = useRef<((text: string) => void) | null>(null);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    filter: true,
    groupby: true,
    sort: true,
    join: false,
  });

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const setNested = (section: string, key: string, value: any) => {
    const current = config[section] ?? {};
    setConfig(section, { ...current, [key]: value });
  };

  // Insert text at cursor in SQL editor via CodeEditor imperative API
  const insertAtCursor = (text: string) => {
    if (sqlInsertRef.current) {
      sqlInsertRef.current(text);
    } else {
      setConfig('sql', (config.sql ?? '') + text);
    }
  };

  // SQL templates using actual column names when available
  const templates = useMemo(() => {
    const cols = upstreamColumns;
    const c1 = cols[0] ?? 'column';
    const c2 = cols[1] ?? 'value';
    return [
      { label: 'Filter', sql: `WHERE ${c1} = 'value'` },
      { label: 'Group', sql: `SELECT ${c1}, SUM(${c2}) FROM data\nGROUP BY ${c1}` },
      { label: 'Sort', sql: `ORDER BY ${c1} ASC` },
      { label: 'Filter+Sort', sql: `WHERE ${c2} > 0\nORDER BY ${c2} DESC` },
    ];
  }, [upstreamColumns]);

  return (
    <>
      {/* Mode toggle */}
      <div className="query-mode-toggle">
        <button
          className={mode === 'form' ? 'active' : ''}
          onClick={() => setConfig('mode', 'form')}
        >
          Form
        </button>
        <button
          className={mode === 'sql' ? 'active' : ''}
          onClick={() => setConfig('mode', 'sql')}
        >
          SQL
        </button>
      </div>

      {mode === 'sql' ? (
        <>
          {/* Input context bar */}
          <div className="sql-context">
            <span className="sql-context-label">Input</span>
            {upstreamColumns.length > 0 ? (
              <>
                <span className="sql-context-sep">&middot;</span>
                <span className="sql-context-label">{upstreamColumns.length} columns</span>
                <span className="sql-context-sep">&middot;</span>
                <code className="sql-context-table">FROM data</code>
                <span className="sql-context-note">optional</span>
              </>
            ) : (
              <span className="sql-context-note">run pipeline to see columns</span>
            )}
          </div>

          {/* Column pills — click to insert */}
          {upstreamColumns.length > 0 && (
            <div className="sql-columns">
              {upstreamColumns.map((col) => (
                <button
                  key={col}
                  className="sql-col-pill"
                  onClick={() => insertAtCursor(col)}
                  title={`Insert "${col}" at cursor`}
                >
                  {col}
                </button>
              ))}
            </div>
          )}

          {/* SQL editor */}
          <div className="field-group">
            <label>SQL Query</label>
            <CodeEditor
              value={config.sql ?? ''}
              onChange={(val) => setConfig('sql', val)}
              language="sql"
              placeholder="WHERE column > 20\nORDER BY column DESC"
              minHeight="140px"
              insertRef={sqlInsertRef}
            />
          </div>

          {/* Templates */}
          <div className="sql-templates">
            <span className="sql-templates-label">Templates:</span>
            {templates.map((t) => (
              <button
                key={t.label}
                className="sql-template-btn"
                onClick={() => setConfig('sql', t.sql)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {upstreamColumns.length === 0 && (
            <div className="sql-hint">
              Just write clauses directly — <code>FROM data</code> is added automatically.
            </div>
          )}
        </>
      ) : (
        <>
          {/* Filter section */}
          <div className="query-section">
            <div className="query-section-header" onClick={() => toggleSection('filter')}>
              <span className="query-section-chevron">{openSections.filter ? '\u25BE' : '\u25B8'}</span>
              <span>WHERE (Filter)</span>
              {config.filter?.column && <span className="query-section-active">&bull;</span>}
            </div>
            {openSections.filter && (
              <div className="query-section-body">
                <div className="field-group">
                  <label>Column</label>
                  <input
                    type="text"
                    value={config.filter?.column ?? ''}
                    onChange={(e) => setNested('filter', 'column', e.target.value)}
                    placeholder="column_name"
                  />
                </div>
                <div className="field-group">
                  <label>Operator</label>
                  <select
                    value={config.filter?.operator ?? 'eq'}
                    onChange={(e) => setNested('filter', 'operator', e.target.value)}
                  >
                    <option value="eq">eq (=)</option>
                    <option value="ne">ne (!=)</option>
                    <option value="gt">gt (&gt;)</option>
                    <option value="lt">lt (&lt;)</option>
                    <option value="ge">ge (&gt;=)</option>
                    <option value="le">le (&lt;=)</option>
                  </select>
                </div>
                <div className="field-group">
                  <label>Value</label>
                  <input
                    type="text"
                    value={config.filter?.value ?? ''}
                    onChange={(e) => setNested('filter', 'value', e.target.value)}
                    placeholder="filter value"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Group By section */}
          <div className="query-section">
            <div className="query-section-header" onClick={() => toggleSection('groupby')}>
              <span className="query-section-chevron">{openSections.groupby ? '\u25BE' : '\u25B8'}</span>
              <span>GROUP BY</span>
              {config.groupby?.keys?.length > 0 && <span className="query-section-active">&bull;</span>}
            </div>
            {openSections.groupby && (
              <div className="query-section-body">
                <div className="field-group">
                  <label>Group Keys (comma-separated)</label>
                  <input
                    type="text"
                    value={Array.isArray(config.groupby?.keys) ? config.groupby.keys.join(', ') : (config.groupby?.keys ?? '')}
                    onChange={(e) => {
                      const keys = e.target.value
                        .split(',')
                        .map((s: string) => s.trim())
                        .filter(Boolean);
                      setNested('groupby', 'keys', keys);
                    }}
                    placeholder="id1, id2"
                  />
                </div>
                <div className="field-group">
                  <label>Aggregations</label>
                  <AggEditor
                    aggs={Array.isArray(config.groupby?.aggs) ? config.groupby.aggs : []}
                    onChange={(aggs) => setNested('groupby', 'aggs', aggs)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Sort section */}
          <div className="query-section">
            <div className="query-section-header" onClick={() => toggleSection('sort')}>
              <span className="query-section-chevron">{openSections.sort ? '\u25BE' : '\u25B8'}</span>
              <span>ORDER BY (Sort)</span>
              {config.sort?.columns?.length > 0 && <span className="query-section-active">&bull;</span>}
            </div>
            {openSections.sort && (
              <div className="query-section-body">
                <div className="field-group">
                  <label>Sort Columns</label>
                  <SortColumnsEditor
                    columns={Array.isArray(config.sort?.columns) ? config.sort.columns : []}
                    onChange={(cols) => setNested('sort', 'columns', cols)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Join section */}
          <div className="query-section">
            <div className="query-section-header" onClick={() => toggleSection('join')}>
              <span className="query-section-chevron">{openSections.join ? '\u25BE' : '\u25B8'}</span>
              <span>JOIN</span>
              {config.join?.right_file && <span className="query-section-active">&bull;</span>}
            </div>
            {openSections.join && (
              <div className="query-section-body">
                <div className="field-group">
                  <label>Right Table (CSV Path)</label>
                  <div className="file-input-row">
                    <input
                      type="text"
                      value={config.join?.right_file ?? ''}
                      onChange={(e) => setNested('join', 'right_file', e.target.value)}
                      placeholder="/path/to/right.csv"
                    />
                    <button
                      className="browse-btn"
                      onClick={() => {
                        setFileBrowserTarget('join_right_file');
                        setShowFileBrowser(true);
                      }}
                      title="Browse files"
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M1 3.5C1 2.67 1.67 2 2.5 2H6l1.5 1.5H13.5C14.33 3.5 15 4.17 15 5V12.5C15 13.33 14.33 14 13.5 14H2.5C1.67 14 1 13.33 1 12.5V3.5Z" fill="currentColor" opacity="0.7"/>
                      </svg>
                    </button>
                  </div>
                  {showFileBrowser && fileBrowserTarget === 'join_right_file' && (
                    <FileBrowser
                      onSelect={(path) => {
                        setNested('join', 'right_file', path);
                        setShowFileBrowser(false);
                      }}
                      onClose={() => setShowFileBrowser(false)}
                    />
                  )}
                </div>
                <div className="field-group">
                  <label>Join Keys (comma-separated)</label>
                  <input
                    type="text"
                    value={Array.isArray(config.join?.keys) ? config.join.keys.join(', ') : (config.join?.keys ?? '')}
                    onChange={(e) => {
                      const keys = e.target.value
                        .split(',')
                        .map((s: string) => s.trim())
                        .filter(Boolean);
                      setNested('join', 'keys', keys);
                    }}
                    placeholder="key1, key2"
                  />
                </div>
                <div className="field-group">
                  <label>Join Type</label>
                  <select
                    value={config.join?.how ?? 'inner'}
                    onChange={(e) => setNested('join', 'how', e.target.value)}
                  >
                    <option value="inner">Inner</option>
                    <option value="left">Left</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}

/* ---------- Agg editor sub-component ---------- */

interface Agg {
  column: string;
  op: string;
}

function AggEditor({
  aggs,
  onChange,
}: {
  aggs: Agg[];
  onChange: (aggs: Agg[]) => void;
}) {
  const ops = ['sum', 'avg', 'min', 'max', 'count'];

  const update = (idx: number, field: keyof Agg, value: string) => {
    const next = [...aggs];
    next[idx] = { ...next[idx], [field]: value };
    onChange(next);
  };

  const add = () => onChange([...aggs, { column: '', op: 'sum' }]);

  const remove = (idx: number) => {
    const next = aggs.filter((_, i) => i !== idx);
    onChange(next);
  };

  return (
    <>
      {aggs.map((agg, i) => (
        <div className="array-item" key={i}>
          <input
            type="text"
            value={agg.column}
            onChange={(e) => update(i, 'column', e.target.value)}
            placeholder="column"
          />
          <select value={agg.op} onChange={(e) => update(i, 'op', e.target.value)}>
            {ops.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
          <button className="remove-btn" onClick={() => remove(i)}>
            &times;
          </button>
        </div>
      ))}
      <button className="add-btn" onClick={add}>
        + Add aggregation
      </button>
    </>
  );
}

/* ---------- Sort columns editor sub-component ---------- */

interface SortCol {
  name: string;
  descending?: boolean;
}

/* ---------- PDF Render inspector sub-component ---------- */

const DEFAULT_TEMPLATE = `# Data Report

{{columns: 55, 45}}
**TEIDE ANALYTICS**
Data Processing Report
|||
**Date:** February 2026
**Dataset:** {{row_count}} rows
{{/columns}}

---

## Key Metrics

{{metrics}}
Groups | v1_sum | count | ,.0f
Total Sum | v1_sum | sum | ,.0f
{{/metrics}}

## Distribution

{{chart: bar, x=id1, y=v1_sum, width=700, height=280}}

---

## Data Table

{{table: max_rows=200}}
`;

const TEMPLATE_REFERENCE = `# Template Reference

## Markdown
# H1  ## H2  ### H3
**bold**  *italic*
--- (horizontal rule)
| col1 | col2 |  (static table)

## Directives
{{columns: 50, 50}}...|||...{{/columns}}
{{columns: 40, 60 | bg=#4AAECC}}...|||...{{/columns}}
{{box}}...{{/box}}
{{box | bg=#f0f0f0}}...{{/box}}
{{kv}}Label | Value{{/kv}}
{{metrics}}Label | column | agg | format{{/metrics}}
{{chart: bar, x=col, y=col, width=500, height=300}}
{{table: max_rows=200, totals=col1;col2}}
{{image: /path/to/file.png, width=200, align=center}}
{{page_break}}
{{spacer: 20}}

## Variables
{{row_count}}  {{col_count}}`;

function PdfRenderInspector({
  config,
  setConfig,
}: {
  config: Record<string, any>;
  setConfig: (key: string, value: any) => void;
}) {
  const theme = config.theme || { primary_color: '#4b6777', font_family: 'Helvetica', font_size: 9 };

  const [showTheme, setShowTheme] = useState(false);
  const [showRef, setShowRef] = useState(false);

  const templateValue = config.template ?? DEFAULT_TEMPLATE;

  const onTemplateChange = (val: string) => {
    setConfig('template', val);
    if (config.sections) {
      setConfig('sections', undefined);
    }
  };

  const setThemeField = (key: string, value: any) => {
    setConfig('theme', { ...theme, [key]: value });
  };

  return (
    <>
      {/* Global settings */}
      <div className="field-group">
        <label>Output Path</label>
        <input type="text" value={config.output_path ?? 'report.pdf'}
          onChange={(e) => setConfig('output_path', e.target.value)} placeholder="report.pdf" />
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Page Size</label>
          <select value={config.page_size ?? 'A4'} onChange={(e) => setConfig('page_size', e.target.value)} style={{ width: '100%' }}>
            <option value="A4">A4</option><option value="Letter">Letter</option>
            <option value="A3">A3</option><option value="Legal">Legal</option>
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Orientation</label>
          <select value={config.orientation ?? 'portrait'} onChange={(e) => setConfig('orientation', e.target.value)} style={{ width: '100%' }}>
            <option value="portrait">Portrait</option><option value="landscape">Landscape</option>
          </select>
        </div>
      </div>

      {/* Theme collapsible */}
      <div className="pdf-theme-section">
        <div className="pdf-theme-header" onClick={() => setShowTheme(!showTheme)}>
          <span className="query-section-chevron">{showTheme ? '\u25BE' : '\u25B8'}</span>
          <span>Theme</span>
        </div>
        {showTheme && (
          <div className="pdf-theme-body">
            <div className="field-group">
              <label>Primary Color</label>
              <input type="color" value={theme.primary_color ?? '#4b6777'}
                onChange={(e) => setThemeField('primary_color', e.target.value)} />
            </div>
            <div className="field-group">
              <label>Font Family</label>
              <select value={theme.font_family ?? 'Helvetica'} onChange={(e) => setThemeField('font_family', e.target.value)}>
                <option value="Helvetica">Helvetica</option>
                <option value="Times-Roman">Times Roman</option>
                <option value="Courier">Courier</option>
              </select>
            </div>
            <div className="field-group">
              <label>Font Size</label>
              <input type="number" value={theme.font_size ?? 9} min={6} max={24}
                onChange={(e) => setThemeField('font_size', parseInt(e.target.value) || 9)} />
            </div>
            <div className="field-group">
              <div className="checkbox-row">
                <input type="checkbox" checked={config.show_header ?? true}
                  onChange={(e) => setConfig('show_header', e.target.checked)} />
                <span>Page Header</span>
              </div>
            </div>
            <div className="field-group">
              <div className="checkbox-row">
                <input type="checkbox" checked={config.show_footer ?? true}
                  onChange={(e) => setConfig('show_footer', e.target.checked)} />
                <span>Page Footer</span>
              </div>
            </div>
            <div className="field-group">
              <label>Footer Text</label>
              <input type="text" value={config.footer_text ?? ''}
                onChange={(e) => setConfig('footer_text', e.target.value)}
                placeholder="Leave blank for page numbers" />
            </div>
          </div>
        )}
      </div>

      {/* Template editor with help button */}
      <div style={{ position: 'relative', marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Document Template</label>
          <button
            className="pdf-help-btn"
            onClick={() => setShowRef(!showRef)}
            title="Show syntax help"
          >?</button>
        </div>
        {showRef && (
          <div className="pdf-ref-body">
            <pre>{TEMPLATE_REFERENCE}</pre>
          </div>
        )}
        <CodeEditor
          value={templateValue}
          onChange={onTemplateChange}
          language="markdown"
          placeholder="# My Report\n\nWrite your template here..."
          minHeight="360px"
        />
      </div>
    </>
  );
}

/* (Section editor components removed — replaced by markdown template editor above) */

function SortColumnsEditor({
  columns,
  onChange,
}: {
  columns: SortCol[];
  onChange: (cols: SortCol[]) => void;
}) {
  const update = (idx: number, field: string, value: any) => {
    const next = [...columns];
    next[idx] = { ...next[idx], [field]: value };
    onChange(next);
  };

  const add = () => onChange([...columns, { name: '', descending: false }]);

  const remove = (idx: number) => {
    const next = columns.filter((_, i) => i !== idx);
    onChange(next);
  };

  return (
    <>
      {columns.map((col, i) => (
        <div className="array-item" key={i}>
          <input
            type="text"
            value={col.name}
            onChange={(e) => update(i, 'name', e.target.value)}
            placeholder="column name"
          />
          <div className="checkbox-row">
            <input
              type="checkbox"
              checked={col.descending ?? false}
              onChange={(e) => update(i, 'descending', e.target.checked)}
            />
            <span style={{ fontSize: 11 }}>DESC</span>
          </div>
          <button className="remove-btn" onClick={() => remove(i)}>
            &times;
          </button>
        </div>
      ))}
      <button className="add-btn" onClick={add}>
        + Add column
      </button>
    </>
  );
}
