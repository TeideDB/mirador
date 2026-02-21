"""kdb+ streaming source node -- subscribes to a kdb+ tickerplant."""

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
            },
            "required": ["host", "port"],
        },
    )

    def __init__(self):
        self._adapter = None
        self._callback = None

    def setup(self, config: dict[str, Any]) -> None:
        from mirador.app import get_teide

        lib = get_teide()
        host = config["host"]
        port = config["port"]
        self._adapter = KDBAdapter(lib, f"{host}:{port}")

        init_expr = config.get("init_expr")
        if init_expr:
            self._adapter.asyn(init_expr)

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._callback = callback

        def on_message(data):
            if isinstance(data, dict):
                self._callback(data)
            elif _TeideTable is not None and isinstance(data, _TeideTable):
                self._callback({
                    "df": data,
                    "rows": len(data),
                    "columns": data.columns,
                })
            else:
                self._callback({"data": data})

        self._adapter.subscribe(on_message)

    def unsubscribe(self) -> None:
        if self._adapter:
            self._adapter.unsubscribe()

    def execute(self, inputs: dict[str, Any], config: dict[str, Any], env=None) -> dict[str, Any]:
        return {}
