interface Props {
  data?: { rows: Record<string, unknown>[]; columns: string[] };
  config: Record<string, unknown>;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  sort?: { column: string; desc: boolean };
  onSort?: (column: string) => void;
}

export default function TableWidget({ data, page, pageSize, total, onPageChange, sort, onSort }: Props) {
  if (!data || !data.rows.length) {
    return <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No data. Click Refresh.</div>;
  }

  const { rows, columns } = data;

  // When using server-side pagination, show all rows as-is (already paged).
  // For local-only mode (no onPageChange), cap at 50 rows.
  const maxRows = onPageChange ? rows.length : 50;
  const displayRows = rows.slice(0, maxRows);

  const totalRows = total ?? rows.length;
  const currentPage = page ?? 1;
  const currentPageSize = pageSize ?? maxRows;
  const totalPages = Math.max(1, Math.ceil(totalRows / currentPageSize));

  return (
    <div style={{ overflow: 'auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <table className="widget-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => onSort?.(col)}
                  style={{ cursor: onSort ? 'pointer' : undefined, userSelect: 'none' }}
                >
                  {col}
                  {sort?.column === col ? (sort.desc ? ' \u25BC' : ' \u25B2') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col}>{String(row[col] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {onPageChange && totalPages > 1 ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 6px', fontSize: 11, color: 'var(--text-muted)' }}>
          <button disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} style={{ fontSize: 11 }}>
            Prev
          </button>
          <span>Page {currentPage} of {totalPages}</span>
          <button disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)} style={{ fontSize: 11 }}>
            Next
          </button>
          <span style={{ marginLeft: 'auto' }}>{totalRows} rows</span>
        </div>
      ) : !onPageChange && rows.length > maxRows ? (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '4px 6px' }}>
          Showing {maxRows} of {rows.length} rows
        </div>
      ) : null}
    </div>
  );
}
