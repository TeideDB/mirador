"""Data grid output node."""

from typing import Any
from mirador.nodes.base import BaseNode, NodeMeta, NodePort


class GridNode(BaseNode):
    meta = NodeMeta(
        id="grid",
        label="Data Grid",
        category="output",
        description="Display data as an interactive table",
        inputs=[NodePort(name="in", description="Dataframe to display")],
        outputs=[],
        config_schema={
            "type": "object",
            "properties": {
                "page_size": {"type": "integer", "title": "Page Size", "default": 100},
            },
        },
    )

    def execute(self, inputs: dict[str, Any], config: dict[str, Any], env=None) -> dict[str, Any]:
        page_size = config.get("page_size", 100)

        # Pre-flattened data (from streaming sources)
        if "rows" in inputs and "columns" in inputs:
            rows = inputs["rows"][:page_size]
            return {
                "rows": rows,
                "columns": inputs["columns"],
                "total": inputs.get("total", len(rows)),
            }

        # Teide Table or similar object
        table = inputs.get("df")
        if table is None:
            return {"rows": [], "columns": [], "total": 0}

        columns = inputs.get("columns", table.columns if hasattr(table, 'columns') else [])
        n = len(table)
        data = table.to_dict()

        rows = []
        for i in range(min(n, page_size)):
            row = {col: data[col][i] for col in columns}
            rows.append(row)

        return {
            "rows": rows,
            "columns": columns,
            "total": n,
        }
