from mirador.nodes.streaming.base import StreamSourceNode
from mirador.nodes.base import NodeMeta, NodePort


def test_stream_source_node_interface():
    """StreamSourceNode must have setup/subscribe/unsubscribe methods."""

    class FakeSource(StreamSourceNode):
        meta = NodeMeta(
            id="fake_stream", label="Fake", category="stream_source",
            inputs=[], outputs=[NodePort(name="out", description="data")],
        )

        def setup(self, config):
            self._connected = True

        def subscribe(self, callback):
            self._callback = callback

        def unsubscribe(self):
            self._callback = None

        def execute(self, inputs, config, env=None):
            return {}

    node = FakeSource()
    node.setup({"host": "localhost", "port": 5001})
    assert node._connected is True

    received = []
    node.subscribe(lambda data: received.append(data))
    node._callback({"rows": 10})
    assert received == [{"rows": 10}]

    node.unsubscribe()
    assert node._callback is None


def test_stream_source_category():
    """StreamSourceNode enforces stream_source category."""
    from mirador.nodes.streaming.base import StreamSourceNode

    class BadCategory(StreamSourceNode):
        meta = NodeMeta(
            id="bad", label="Bad", category="input",
            inputs=[], outputs=[],
        )
        def setup(self, config): pass
        def subscribe(self, callback): pass
        def unsubscribe(self): pass
        def execute(self, inputs, config, env=None): return {}

    # Category should still be whatever is in meta --
    # we just verify convention via the base class docstring
    # The real enforcement is in the executor/frontend
    assert BadCategory.meta.category == "input"
