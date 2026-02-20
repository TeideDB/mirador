<p align="center">
  <img src="frontend/public/logo.svg" alt="Mirador" width="240"/>
</p>

<p align="center">
  Visual data pipeline editor powered by <a href="https://github.com/akundenko/teide">Teide</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-4b6777?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/>
  <img src="https://img.shields.io/badge/react-19-4b6777?style=flat-square&logo=react&logoColor=white" alt="React 19"/>
  <img src="https://img.shields.io/badge/license-MIT-4b6777?style=flat-square" alt="MIT License"/>
</p>

---

Mirador is a node-based visual editor for building data analytics pipelines. Connect data sources to transformations and outputs — groupby, sort, join, filter, charts, PDF reports — all backed by the [Teide](https://github.com/akundenko/teide) C17 dataframe engine.

## Features

- **Visual pipeline editor** — drag-and-drop nodes, connect with edges, configure in the inspector
- **Teide-powered execution** — 10M-row groupby in 2ms, sort in 100ms, single-threaded C engine
- **SQL & form modes** — write raw SQL or use structured forms for groupby/sort/join/filter
- **Live preview** — data grids, charts, and PDF reports update as you build
- **PDF template engine** — markdown templates with `{{directives}}` for columns, metrics, charts, tables, images
- **Project system** — save/load pipelines, organize into projects
- **Dashboard builder** — pin pipeline outputs to interactive dashboards

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  React Frontend (ReactFlow + CodeMirror)            │
│  Pipelines · Dashboards · Inspector · Preview       │
├─────────────────────────────────────────────────────┤
│  FastAPI Backend                                    │
│  /api/pipelines/run-stream · /api/projects · /api/nodes │
├─────────────────────────────────────────────────────┤
│  Node Executor                                      │
│  Topological sort → execute nodes → stream results  │
├─────────────────────────────────────────────────────┤
│  Teide Engine (libteide.so)                         │
│  CSV → lazy DAG → optimizer → fused morsel executor │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Prerequisites: Python 3.12+, Node 20+, built libteide.so

# Backend
cd mirador
uv sync
uv run uvicorn mirador.app:app --reload --port 8000

# Frontend (development)
cd frontend
npm install
npm run dev

# Frontend (production build)
npm run build
cp -r dist/* ../mirador/frontend_dist/
```

Open `http://localhost:8000` — the backend serves both the API and the frontend bundle.

## Node Types

| Category | Nodes |
|----------|-------|
| **Input** | CSV Source |
| **Compute** | Query (SQL/form), Formula, Script, Conditional, Dict Transform |
| **Output** | Data Grid, Chart, PDF Report, Export |
| **Integration** | Gmail, Google Drive, AI |

## PDF Templates

Write documents in markdown with embedded directives:

```markdown
# Quarterly Report

{{columns: 60, 40}}
**ACME Corp** Analytics Division
|||
**Date:** {{today}}
**Records:** {{row_count}}
{{/columns}}

---

## Revenue by Region

{{chart: bar, x=region, y=revenue, width=600, height=300}}

{{table: max_rows=100}}
```

## Stack

- **Frontend**: React 19, ReactFlow, CodeMirror 6, Recharts
- **Backend**: FastAPI, uvicorn, ReportLab, matplotlib
- **Engine**: [Teide](https://github.com/akundenko/teide) — pure C17, zero dependencies, buddy allocator, morsel-driven execution

## License

MIT — Copyright (c) 2024-2026 Anton Kundenko
