import { useCallback, useEffect, useRef, useState } from 'react';
import useStore, { type DashboardWidget } from '../store/useStore';
import { fetchDashboard, saveDashboard as apiSaveDashboard, refreshDashboardData } from '../api/client';
import WidgetCard from '../components/dashboard/WidgetCard';
import WidgetConfigPanel from '../components/dashboard/WidgetConfigPanel';

let widgetIdCounter = 0;

type WidgetType = DashboardWidget['type'];

const GRID_COLS = 12;
const ROW_HEIGHT = 80;
const GAP = 12;

const widgetTypes: { type: WidgetType; label: string }[] = [
  { type: 'table', label: 'Table' },
  { type: 'bar_chart', label: 'Bar Chart' },
  { type: 'line_chart', label: 'Line Chart' },
  { type: 'pie_chart', label: 'Pie Chart' },
  { type: 'stat_card', label: 'Stat Card' },
];

interface DragState {
  widgetId: string;
  mode: 'move' | 'resize';
  startX: number;
  startY: number;
  origLayout: { x: number; y: number; w: number; h: number };
}

export default function DashboardEditorPage() {
  const slug = useStore((s) => s.currentProjectSlug);
  const dashName = useStore((s) => s.currentDashboardName);
  const setView = useStore((s) => s.setView);
  const dashboardDef = useStore((s) => s.dashboardDef);
  const setDashboardDef = useStore((s) => s.setDashboardDef);
  const dashboardData = useStore((s) => s.dashboardData);
  const setDashboardData = useStore((s) => s.setDashboardData);
  const addWidget = useStore((s) => s.addWidget);
  const removeWidget = useStore((s) => s.removeWidget);
  const selectedWidgetId = useStore((s) => s.selectedWidgetId);
  const selectWidget = useStore((s) => s.selectWidget);
  const updateWidgetLayout = useStore((s) => s.updateWidgetLayout);
  const addDataSource = useStore((s) => s.addDataSource);
  const removeDataSource = useStore((s) => s.removeDataSource);

  const [showAddDs, setShowAddDs] = useState(false);
  const [dsForm, setDsForm] = useState({ workflow_name: '', node_id: '', alias: '' });
  const [showAddWidget, setShowAddWidget] = useState(false);

  const gridRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [dragPreview, setDragPreview] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  // Load dashboard on mount
  useEffect(() => {
    if (!slug || !dashName) return;
    (async () => {
      const data = await fetchDashboard(slug, dashName);
      if (data) {
        setDashboardDef(data);
      } else {
        setDashboardDef({ name: dashName, data_sources: [], widgets: [], grid_cols: 12 });
      }
    })();
    return () => { setDashboardDef(null); };
  }, [slug, dashName, setDashboardDef]);

  const handleSave = useCallback(async () => {
    if (!slug || !dashName || !dashboardDef) return;
    await apiSaveDashboard(slug, dashName, dashboardDef);
  }, [slug, dashName, dashboardDef]);

  const handleRefresh = useCallback(async () => {
    if (!slug || !dashName) return;
    const data = await refreshDashboardData(slug, dashName);
    setDashboardData(data);
  }, [slug, dashName, setDashboardData]);

  const handleAddWidget = (type: WidgetType) => {
    const id = `widget_${++widgetIdCounter}`;
    const widget: DashboardWidget = {
      id,
      type,
      title: type.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      layout: { x: 0, y: 0, w: 4, h: 3 },
      data_source: dashboardDef?.data_sources[0]?.alias ?? '',
      config: {},
    };
    addWidget(widget);
    setShowAddWidget(false);
    selectWidget(id);
  };

  const handleAddDs = () => {
    if (!dsForm.alias.trim()) return;
    addDataSource({
      workflow_name: dsForm.workflow_name,
      node_id: dsForm.node_id,
      alias: dsForm.alias.trim(),
    });
    setDsForm({ workflow_name: '', node_id: '', alias: '' });
    setShowAddDs(false);
  };

  // Convert pixel offset to grid cell
  const pxToGrid = useCallback((px: number, cellSize: number) => {
    return Math.max(0, Math.round(px / cellSize));
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent, widgetId: string, mode: 'move' | 'resize') => {
    e.preventDefault();
    e.stopPropagation();
    const w = dashboardDef?.widgets.find((w) => w.id === widgetId);
    if (!w) return;
    dragRef.current = {
      widgetId,
      mode,
      startX: e.clientX,
      startY: e.clientY,
      origLayout: { ...w.layout },
    };
    setDragPreview({ ...w.layout });
    selectWidget(widgetId);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, [dashboardDef, selectWidget]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || !gridRef.current) return;

    const gridRect = gridRef.current.getBoundingClientRect();
    const colW = (gridRect.width - GAP * (GRID_COLS - 1)) / GRID_COLS + GAP;
    const rowH = ROW_HEIGHT + GAP;

    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;

    if (drag.mode === 'move') {
      const newX = Math.max(0, Math.min(GRID_COLS - drag.origLayout.w,
        drag.origLayout.x + pxToGrid(dx, colW)));
      const newY = Math.max(0, drag.origLayout.y + pxToGrid(dy, rowH));
      setDragPreview({ ...drag.origLayout, x: newX, y: newY });
    } else {
      const newW = Math.max(1, Math.min(GRID_COLS - drag.origLayout.x,
        drag.origLayout.w + pxToGrid(dx, colW)));
      const newH = Math.max(1, drag.origLayout.h + pxToGrid(dy, rowH));
      setDragPreview({ ...drag.origLayout, w: newW, h: newH });
    }
  }, [pxToGrid]);

  const onPointerUp = useCallback(() => {
    const drag = dragRef.current;
    if (!drag || !dragPreview) {
      dragRef.current = null;
      setDragPreview(null);
      return;
    }
    updateWidgetLayout(drag.widgetId, dragPreview);
    dragRef.current = null;
    setDragPreview(null);
  }, [dragPreview, updateWidgetLayout]);

  if (!dashboardDef) return null;

  const selectedWidget = dashboardDef.widgets.find((w) => w.id === selectedWidgetId);
  const draggingId = dragRef.current?.widgetId ?? null;

  return (
    <div className="dashboard-editor">
      <div className="dashboard-toolbar">
        <button className="back-btn" onClick={() => setView('dashboards')} title="Back to dashboards">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 2L4 7l5 5"/>
          </svg>
        </button>
        <span className="toolbar-workflow-name">{dashName}</span>
        <div className="toolbar-spacer" />
        <button onClick={() => setShowAddWidget(!showAddWidget)}>+ Add Widget</button>
        <button className="primary-btn" onClick={handleSave}>Save</button>
        <button onClick={handleRefresh}>Refresh Data</button>
      </div>

      <div className="dashboard-main">
        {/* Left: Data Sources */}
        <div className="dashboard-side-panel">
          <h4>Data Sources</h4>
          <ul className="ds-list">
            {dashboardDef.data_sources.map((ds) => (
              <li key={ds.alias}>
                <span>{ds.alias}</span>
                <button onClick={() => removeDataSource(ds.alias)}>&times;</button>
              </li>
            ))}
          </ul>
          <button className="list-card-action" onClick={() => setShowAddDs(!showAddDs)}>+ Add Source</button>
          {showAddDs && (
            <div className="add-ds-form">
              <input
                placeholder="Workflow name"
                value={dsForm.workflow_name}
                onChange={(e) => setDsForm({ ...dsForm, workflow_name: e.target.value })}
              />
              <input
                placeholder="Node ID"
                value={dsForm.node_id}
                onChange={(e) => setDsForm({ ...dsForm, node_id: e.target.value })}
              />
              <input
                placeholder="Alias"
                value={dsForm.alias}
                onChange={(e) => setDsForm({ ...dsForm, alias: e.target.value })}
              />
              <button onClick={handleAddDs}>Add</button>
            </div>
          )}

          {showAddWidget && (
            <>
              <h4 style={{ marginTop: 16 }}>Add Widget</h4>
              <div className="widget-type-grid">
                {widgetTypes.map((wt) => (
                  <button key={wt.type} className="widget-type-btn" onClick={() => handleAddWidget(wt.type)}>
                    {wt.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Center: Grid */}
        <div className="dashboard-grid-container">
          {dashboardDef.widgets.length === 0 ? (
            <div className="list-empty">No widgets yet. Click "+ Add Widget" to begin.</div>
          ) : (
            <div
              ref={gridRef}
              style={{ display: 'grid', gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`, gap: GAP, gridAutoRows: ROW_HEIGHT, position: 'relative' }}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            >
              {dashboardDef.widgets.map((w) => {
                const layout = (draggingId === w.id && dragPreview) ? dragPreview : w.layout;
                return (
                  <div
                    key={w.id}
                    className={`dashboard-widget-wrapper${draggingId === w.id ? ' dragging' : ''}`}
                    style={{
                      gridColumn: `${layout.x + 1} / span ${layout.w}`,
                      gridRow: `${layout.y + 1} / span ${layout.h}`,
                      position: 'relative',
                    }}
                    onClick={() => selectWidget(w.id)}
                  >
                    <div
                      className="widget-drag-handle"
                      onPointerDown={(e) => onPointerDown(e, w.id, 'move')}
                    />
                    <WidgetCard
                      widget={w}
                      data={dashboardData[w.data_source]}
                      selected={selectedWidgetId === w.id}
                      onRemove={() => removeWidget(w.id)}
                    />
                    <div
                      className="widget-resize-handle"
                      onPointerDown={(e) => onPointerDown(e, w.id, 'resize')}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: Widget Config */}
        {selectedWidget && (
          <WidgetConfigPanel widget={selectedWidget} />
        )}
      </div>
    </div>
  );
}
