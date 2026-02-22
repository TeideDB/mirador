"""kdb+ streaming source node -- subscribes to a kdb+ tickerplant."""

import logging
from typing import Any, Callable

from mirador.nodes.base import NodeMeta, NodePort
from mirador.nodes.streaming.base import StreamSourceNode

try:
    from teide.io.kdb import KDBAdapter
except ImportError:
    KDBAdapter = None  # type: ignore[assignment,misc]

try:
    from teide.api import Table as _TeideTable
except ImportError:
    _TeideTable = None  # type: ignore[assignment,misc]

_log = logging.getLogger(__name__)


def _flatten_kdb_data(data: Any) -> dict[str, Any]:
    """Convert kdb+ IPC message data to a flat row-oriented dict for downstream nodes.

    Handles keyed tables ({keys: {...}, values: {...}}), upd messages with
    delta wrappers, and plain column-oriented dicts.
    """
    # Extract the actual table data from upd messages
    payload = data
    if isinstance(data, dict) and "data" in data:
        payload = data["data"]

    # Unwrap delta wrapper (e.g. {"delta": {"keys": {...}, "values": {...}}})
    if isinstance(payload, dict) and "delta" in payload:
        payload = payload["delta"]

    return _keyed_table_to_rows(payload)


def _keyed_table_to_rows(payload: Any) -> dict[str, Any]:
    """Convert a keyed table or column dict to row-oriented format."""
    # Handle keyed table: merge keys + values into one column dict
    if isinstance(payload, dict) and "keys" in payload and "values" in payload:
        keys_dict = payload["keys"]
        vals_dict = payload["values"]
        if isinstance(keys_dict, dict) and isinstance(vals_dict, dict):
            merged = {**keys_dict, **vals_dict}
            return _columns_to_rows(merged)

    # Handle plain dict (column-oriented)
    if isinstance(payload, dict):
        # Check if it looks column-oriented (values are lists)
        has_lists = any(isinstance(v, list) for v in payload.values())
        if has_lists:
            return _columns_to_rows(payload)

    # Fallback
    return {"data": payload}


def _columns_to_rows(col_dict: dict) -> dict[str, Any]:
    """Convert a column-oriented dict to row-oriented format."""
    columns = list(col_dict.keys())
    n = 0
    for v in col_dict.values():
        if isinstance(v, list):
            n = len(v)
            break
    rows = []
    for i in range(n):
        row = {}
        for col in columns:
            vals = col_dict[col]
            row[col] = vals[i] if isinstance(vals, list) and i < len(vals) else vals
        rows.append(row)
    return {"rows": rows, "columns": columns, "total": n}


class KdbSourceNode(StreamSourceNode):
    meta = NodeMeta(
        id="kdb_source",
        label="kdb+ Stream",
        category="stream_source",
        description="Subscribe to a kdb+ tickerplant for real-time data",
        inputs=[],
        outputs=[NodePort(name="out", description="Streaming data from kdb+")],
        config_schema={
            "type": "object",
            "properties": {
                "host": {"type": "string", "title": "Host", "default": "localhost"},
                "port": {"type": "integer", "title": "Port", "default": 5001},
                "init_expr": {
                    "type": "string",
                    "title": "Init Expression",
                    "description": "q expression to run on connect (e.g. .u.sub[`trade;`])",
                },
                "subscribe_expr": {
                    "type": "string",
                    "title": "Subscribe Expression",
                    "description": "q expression to send when subscribing (e.g. .u.sub[`trade;`])",
                },
            },
            "required": ["host", "port"],
        },
    )

    def __init__(self):
        self._adapter = None
        self._callback = None
        self._config = {}

    def setup(self, config: dict[str, Any]) -> None:
        self._config = config
        host = config["host"]
        port = config["port"]
        _log.info("KDB setup: connecting to %s:%s", host, port)
        self._adapter = KDBAdapter(None, f"{host}:{port}")

        init_expr = config.get("init_expr")
        if init_expr:
            _log.info("KDB setup: sending init_expr: %s", init_expr)
            result = self._adapter.sync(init_expr)
            _log.info("KDB setup: init_expr result: %s", result)

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._callback = callback

        # Send subscribe expression if configured
        subscribe_expr = self._config.get("subscribe_expr")
        if subscribe_expr:
            _log.info("KDB subscribe: sending subscribe_expr: %s", subscribe_expr)
            self._adapter.asyn(subscribe_expr)

        def on_message(data):
            _log.debug("KDB on_message: type=%s", type(data).__name__)
            result = _flatten_kdb_data(data)
            self._callback(result)

        _log.info("KDB subscribe: starting message listener")
        self._adapter.subscribe(on_message)

    def unsubscribe(self) -> None:
        if self._adapter:
            self._adapter.unsubscribe()

    def execute(self, inputs: dict[str, Any], config: dict[str, Any], env=None) -> dict[str, Any]:
        return {}
