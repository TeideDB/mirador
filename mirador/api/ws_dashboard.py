# mirador/api/ws_dashboard.py
"""WebSocket endpoint for live dashboard data."""

import asyncio
import logging
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected widgets per pipeline: pipeline_key -> {ws -> {widget_id -> view_params}}
_connections: dict[str, dict[WebSocket, dict[str, dict]]] = {}
_connections_lock = threading.Lock()

# Captured event loop for cross-thread notifications
_event_loop: asyncio.AbstractEventLoop | None = None


def notify_data_changed(pipeline_key: str, tables: list[str], row_counts: dict[str, int] | None = None):
    """Called by StreamingExecutor after a tick completes.

    Sends data_changed signal to all connected dashboard WS clients.
    Called from a background thread — uses run_coroutine_threadsafe.
    """
    with _connections_lock:
        conns = _connections.get(pipeline_key, {})
        ws_list = list(conns.keys())

    if not ws_list or _event_loop is None:
        return

    msg: dict[str, Any] = {"event": "data_changed", "tables": tables}
    if row_counts:
        msg["row_counts"] = row_counts

    async def _send_all():
        for ws in ws_list:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    try:
        asyncio.run_coroutine_threadsafe(_send_all(), _event_loop)
    except Exception:
        pass


@router.websocket("/ws/dashboard/{pipeline_key:path}")
async def ws_dashboard(ws: WebSocket, pipeline_key: str):
    """Live dashboard data channel."""
    from mirador.app import get_publish_registry

    global _event_loop
    await ws.accept()

    # Capture the running event loop for cross-thread notifications
    if _event_loop is None:
        _event_loop = asyncio.get_running_loop()

    registry = get_publish_registry()
    entry = registry.get(pipeline_key)
    if entry is None:
        await ws.send_json({"event": "error", "error": f"Pipeline '{pipeline_key}' not running"})
        await ws.close()
        return

    env = entry["env"]

    # Track this connection
    with _connections_lock:
        if pipeline_key not in _connections:
            _connections[pipeline_key] = {}
        _connections[pipeline_key][ws] = {}

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")

            if action == "subscribe":
                widget_id = msg["widget_id"]
                _connections[pipeline_key][ws][widget_id] = {
                    "table": msg.get("table"),
                    "page": msg.get("page", 0),
                    "page_size": msg.get("page_size", 50),
                    "sort": msg.get("sort"),
                    "filters": msg.get("filters"),
                }
                await ws.send_json({"event": "subscribed", "widget_id": widget_id})

            elif action == "fetch":
                widget_id = msg["widget_id"]
                view = _connections[pipeline_key][ws].get(widget_id)
                if not view:
                    await ws.send_json({"event": "error", "error": f"Widget {widget_id} not subscribed"})
                    continue

                table_name = view["table"]
                try:
                    table_data = env.get(table_name)
                except KeyError:
                    await ws.send_json({"event": "error", "error": f"Table '{table_name}' not found"})
                    continue

                page = view.get("page", 0)
                page_size = view.get("page_size", 50)
                result = _query_table(table_data, page, page_size, view.get("sort"), view.get("filters"))
                await ws.send_json({
                    "event": "page",
                    "widget_id": widget_id,
                    **result,
                })

    except WebSocketDisconnect:
        pass
    finally:
        with _connections_lock:
            conns = _connections.get(pipeline_key, {})
            conns.pop(ws, None)
            if not conns:
                _connections.pop(pipeline_key, None)


def _query_table(table_data: Any, page: int, page_size: int,
                 sort: dict | None, filters: list | None) -> dict:
    """Query a table with pagination, sort, filter.

    Supports both raw dict tables (for simple cases) and Teide Table objects.
    """
    # Try Teide Table
    try:
        from teide.api import Table
        if isinstance(table_data, Table):
            total = len(table_data)
            start = page * page_size
            end = min(start + page_size, total)
            sliced = table_data.head(end)
            rows_dict = sliced.to_dict()
            columns = sliced.columns
            rows = []
            for i in range(start, min(end, len(rows_dict.get(columns[0], [])))):
                row = {col: rows_dict[col][i] for col in columns}
                rows.append(row)
            return {"rows": rows, "columns": columns, "total": total}
    except ImportError:
        pass

    # Raw dict format
    if isinstance(table_data, dict):
        rows = table_data.get("rows", [])
        columns = table_data.get("columns", [])
        total = table_data.get("total", len(rows))
        start = page * page_size
        end = start + page_size
        return {"rows": rows[start:end], "columns": columns, "total": total}

    return {"rows": [], "columns": [], "total": 0}
