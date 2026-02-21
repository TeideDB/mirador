"""TableEnv — named table environment for streaming pipelines."""

import threading
from typing import Any


class TableEnv:
    """Thread-safe named table registry.

    Stores named references (typically teide.api.Table objects) that
    init nodes create and streaming processing nodes read/update.
    Dashboard queries also read from this environment.
    """

    def __init__(self):
        self._tables: dict[str, Any] = {}
        self._lock = threading.Lock()

    def set(self, name: str, table: Any) -> None:
        with self._lock:
            self._tables[name] = table

    def get(self, name: str) -> Any:
        with self._lock:
            return self._tables[name]  # raises KeyError if missing

    def drop(self, name: str) -> None:
        with self._lock:
            self._tables.pop(name, None)

    def list(self) -> list[str]:
        with self._lock:
            return list(self._tables.keys())

    def clear(self) -> None:
        with self._lock:
            self._tables.clear()
