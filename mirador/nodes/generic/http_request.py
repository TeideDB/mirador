"""HTTP request node — fetch data from or send data to a URL."""

import csv
import json
import os
import tempfile
from typing import Any

import httpx

from mirador.nodes.base import BaseNode, NodeMeta, NodePort


def _navigate_json_path(data: Any, path: str) -> Any:
    """Navigate a dot-separated path into a nested JSON structure."""
    for key in path.split("."):
        if isinstance(data, dict):
            data = data[key]
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)]
        else:
            raise KeyError(f"Cannot navigate '{key}' in {type(data).__name__}")
    return data


def _to_table(records: list[dict]) -> dict[str, Any]:
    """Convert a list of flat dicts into a Teide Table via temp CSV."""
    from mirador.app import get_teide
    from teide.api import Table

    if not records:
        return {"df": None, "rows": 0, "columns": []}

    columns = list(records[0].keys())

    # Write to a temp CSV, then read with Teide
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)

        lib = get_teide()
        tbl_ptr = lib.read_csv(tmp_path)
        if not tbl_ptr or tbl_ptr < 32:
            raise RuntimeError("Failed to load fetched data into table")
        table = Table(lib, tbl_ptr)
        return {"df": table, "rows": len(table), "columns": table.columns}
    finally:
        os.unlink(tmp_path)


class HttpRequestNode(BaseNode):
    meta = NodeMeta(
        id="http_request",
        label="HTTP Request",
        category="generic",
        description="Fetch data from or send data to a URL",
        inputs=[NodePort(name="in", description="Input data (used in send mode)")],
        outputs=[NodePort(name="out", description="Response data")],
        config_schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "title": "Mode",
                    "enum": ["fetch", "send"],
                    "default": "fetch",
                },
                "url": {"type": "string", "title": "URL"},
                "method": {
                    "type": "string",
                    "title": "Method",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "default": "GET",
                },
                "headers": {
                    "type": "array",
                    "title": "Headers",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                    },
                },
                "body": {
                    "type": "string",
                    "title": "Body",
                    "description": "Request body (POST/PUT in fetch mode)",
                },
                "json_path": {
                    "type": "string",
                    "title": "JSON Path",
                    "description": "Dot-notation path to extract (e.g. data.results)",
                },
                "timeout": {
                    "type": "number",
                    "title": "Timeout (seconds)",
                    "default": 30,
                },
            },
            "required": ["url"],
        },
    )

    def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        mode = config.get("mode", "fetch")
        url = config["url"]
        method = config.get("method", "GET")
        timeout = config.get("timeout", 30)

        # Build headers dict
        headers = {}
        for h in config.get("headers", []) or []:
            if h.get("key"):
                headers[h["key"]] = h.get("value", "")

        if mode == "fetch":
            return self._fetch(url, method, headers, config.get("body"), config.get("json_path"), timeout)
        else:
            return self._send(url, method, headers, inputs, timeout)

    def _fetch(self, url: str, method: str, headers: dict, body: str | None, json_path: str | None, timeout: float) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
        if body and method in ("POST", "PUT"):
            try:
                kwargs["json"] = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                kwargs["content"] = body

        with httpx.Client() as client:
            resp = client.request(method, url, **kwargs)
            resp.raise_for_status()

        data = resp.json()

        if json_path:
            data = _navigate_json_path(data, json_path)

        # Normalize to list of dicts for table conversion
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return {"raw": data, "rows": 0, "columns": []}

        return _to_table(data)

    def _send(self, url: str, method: str, headers: dict, inputs: dict[str, Any], timeout: float) -> dict[str, Any]:
        # Convert upstream df to list of dicts for the payload
        df = inputs.get("df")
        if df is not None:
            payload = df.to_dict()
        else:
            payload = {k: v for k, v in inputs.items() if k not in ("df",)}

        if method == "GET":
            method = "POST"  # default to POST for send mode

        with httpx.Client() as client:
            resp = client.request(method, url, json=payload, headers=headers, timeout=timeout)

        return {
            "status_code": resp.status_code,
            "success": resp.is_success,
            "response_body": resp.text[:10000],
            **inputs,
        }
