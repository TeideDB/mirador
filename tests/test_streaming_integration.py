# tests/test_streaming_integration.py
"""End-to-end integration test: init -> stream source -> processing."""

import time
import threading
from mirador.engine.streaming_executor import StreamingExecutor
from mirador.engine.table_env import TableEnv
from mirador.engine.registry import NodeRegistry
from mirador.nodes.base import BaseNode, NodeMeta, NodePort
from mirador.nodes.streaming.base import StreamSourceNode


class TimerSource(StreamSourceNode):
    """Emits incrementing counters on a timer."""
    meta = NodeMeta(
        id="timer_source", label="Timer", category="stream_source",
        inputs=[], outputs=[NodePort(name="out", description="counter")],
    )

    def setup(self, config):
        self._interval = config.get("interval", 0.01)
        self._count = config.get("count", 5)

    def subscribe(self, callback):
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(callback,), daemon=True)
        self._thread.start()

    def _loop(self, callback):
        for i in range(self._count):
            if not self._running:
                break
            callback({"tick": i})
            time.sleep(self._interval)

    def unsubscribe(self):
        self._running = False
        if hasattr(self, '_thread'):
            self._thread.join(timeout=1.0)

    def execute(self, inputs, config, env=None):
        return {}


class AccumulatorNode(BaseNode):
    """Appends each tick's data to a list in env."""
    meta = NodeMeta(
        id="accumulator", label="Accumulator", category="generic",
        inputs=[NodePort(name="in", description="input")],
        outputs=[NodePort(name="out", description="output")],
    )

    def execute(self, inputs, config, env=None):
        if env:
            try:
                ticks = env.get("ticks")
            except KeyError:
                ticks = []
            ticks.append(inputs.get("tick"))
            env.set("ticks", ticks)
        return {"accumulated": True}


class SetupNode(BaseNode):
    """Init node that creates initial state."""
    meta = NodeMeta(
        id="setup_node", label="Setup", category="init",
        inputs=[], outputs=[],
    )

    def execute(self, inputs, config, env=None):
        if env:
            env.set("ticks", [])
        return {"initialized": True}


def test_full_streaming_pipeline():
    """Init creates state, timer fires 5 ticks, accumulator stores them."""
    reg = NodeRegistry()
    reg.node_types["timer_source"] = TimerSource
    reg.node_types["accumulator"] = AccumulatorNode
    reg.node_types["setup_node"] = SetupNode

    pipeline = {
        "nodes": [
            {"id": "init", "type": "setup_node", "config": {}},
            {"id": "src", "type": "timer_source", "config": {"count": 5, "interval": 0.01}},
            {"id": "acc", "type": "accumulator", "config": {}},
        ],
        "edges": [
            {"source": "src", "target": "acc"},
        ],
    }

    env = TableEnv()
    ticks_done = []
    executor = StreamingExecutor(reg)
    executor.start(pipeline, env, on_tick_complete=lambda e: ticks_done.append(1))

    # Wait for all ticks
    time.sleep(0.3)
    executor.stop()

    assert env.get("ticks") == [0, 1, 2, 3, 4]
    assert len(ticks_done) == 5
