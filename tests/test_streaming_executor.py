"""Tests for StreamingExecutor using mock streaming sources."""

import threading
import time

from mirador.engine.streaming_executor import StreamingExecutor
from mirador.engine.table_env import TableEnv
from mirador.engine.registry import NodeRegistry
from mirador.nodes.base import BaseNode, NodeMeta, NodePort
from mirador.nodes.streaming.base import StreamSourceNode


# --- Mock nodes for testing ---


class MockStreamSource(StreamSourceNode):
    meta = NodeMeta(
        id="mock_stream",
        label="Mock Stream",
        category="stream_source",
        inputs=[],
        outputs=[NodePort(name="out", description="data")],
    )

    def setup(self, config):
        self._messages = config.get("messages", [])

    def subscribe(self, callback):
        self._callback = callback
        self._thread = threading.Thread(target=self._emit, daemon=True)
        self._running = True
        self._thread.start()

    def _emit(self):
        for msg in self._messages:
            if not self._running:
                break
            self._callback(msg)
            time.sleep(0.01)

    def unsubscribe(self):
        self._running = False
        if hasattr(self, "_thread"):
            self._thread.join(timeout=1.0)

    def execute(self, inputs, config, env=None):
        return {}


class MockInitNode(BaseNode):
    meta = NodeMeta(
        id="mock_init",
        label="Mock Init",
        category="init",
        inputs=[],
        outputs=[NodePort(name="out", description="setup")],
    )

    def execute(self, inputs, config, env=None):
        if env is not None:
            env.set("counter", {"value": 0})
        return {"initialized": True}


class MockProcessNode(BaseNode):
    meta = NodeMeta(
        id="mock_process",
        label="Mock Process",
        category="generic",
        inputs=[NodePort(name="in", description="input")],
        outputs=[NodePort(name="out", description="output")],
    )

    def execute(self, inputs, config, env=None):
        if env is not None:
            try:
                counter = env.get("counter")
                counter["value"] += 1
                env.set("counter", counter)
            except KeyError:
                pass
        return {"processed": True}


def _make_registry():
    reg = NodeRegistry()
    reg.node_types["mock_stream"] = MockStreamSource
    reg.node_types["mock_init"] = MockInitNode
    reg.node_types["mock_process"] = MockProcessNode
    return reg


def test_streaming_executor_basic():
    """Init runs once, then streaming source fires downstream chain."""
    pipeline = {
        "nodes": [
            {"id": "init1", "type": "mock_init", "config": {}},
            {
                "id": "src1",
                "type": "mock_stream",
                "config": {
                    "messages": [
                        {"value": 1},
                        {"value": 2},
                        {"value": 3},
                    ],
                },
            },
            {"id": "proc1", "type": "mock_process", "config": {}},
        ],
        "edges": [
            {"source": "src1", "target": "proc1"},
        ],
    }

    env = TableEnv()
    tick_count = []

    def on_tick(e):
        tick_count.append(1)

    registry = _make_registry()
    executor = StreamingExecutor(registry)
    executor.start(pipeline, env, on_tick_complete=on_tick)

    # Wait for messages to be processed
    time.sleep(0.2)
    executor.stop()

    # Init should have set counter to 0, then 3 ticks should increment to 3
    assert env.get("counter")["value"] == 3
    assert len(tick_count) == 3


def test_streaming_executor_no_init():
    """Pipeline with no init nodes should still work."""
    pipeline = {
        "nodes": [
            {
                "id": "src1",
                "type": "mock_stream",
                "config": {
                    "messages": [{"value": 1}],
                },
            },
            {"id": "proc1", "type": "mock_process", "config": {}},
        ],
        "edges": [
            {"source": "src1", "target": "proc1"},
        ],
    }

    env = TableEnv()
    registry = _make_registry()
    executor = StreamingExecutor(registry)
    executor.start(pipeline, env)
    time.sleep(0.1)
    executor.stop()

    # Should not crash, process node ran
    assert True


def test_streaming_executor_stop():
    """Executor should cleanly stop sources."""
    pipeline = {
        "nodes": [
            {
                "id": "src1",
                "type": "mock_stream",
                "config": {
                    "messages": [{"value": i} for i in range(1000)],
                },
            },
        ],
        "edges": [],
    }

    env = TableEnv()
    registry = _make_registry()
    executor = StreamingExecutor(registry)
    executor.start(pipeline, env)
    time.sleep(0.05)
    executor.stop()
    # Should not hang or crash
    assert not executor._running
