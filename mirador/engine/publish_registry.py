"""Registry for published (running) streaming pipelines."""

import threading
from typing import Any


class PublishRegistry:
    """Tracks running streaming pipelines and their environments."""

    def __init__(self):
        self._running: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(self, key: str, env: Any, executor: Any) -> None:
        with self._lock:
            self._running[key] = {"env": env, "executor": executor}

    def unregister(self, key: str) -> dict | None:
        with self._lock:
            return self._running.pop(key, None)

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._running.get(key)

    def list_running(self) -> list[str]:
        with self._lock:
            return list(self._running.keys())
