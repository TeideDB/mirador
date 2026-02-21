"""Tests for kdb+ stream source node (mocked adapter)."""

from unittest.mock import MagicMock, patch
from mirador.nodes.streaming.kdb_source import KdbSourceNode


def test_kdb_source_meta():
    assert KdbSourceNode.meta.category == "stream_source"
    assert KdbSourceNode.meta.id == "kdb_source"


def test_kdb_source_setup_and_subscribe():
    """Test that setup creates adapter and subscribe starts delivery."""
    node = KdbSourceNode()

    mock_adapter = MagicMock()
    mock_lib = MagicMock()

    with patch("mirador.nodes.streaming.kdb_source.KDBAdapter", return_value=mock_adapter), \
         patch("mirador.app.get_teide", return_value=mock_lib):
        node.setup({"host": "localhost", "port": 5001})
        assert node._adapter is mock_adapter

        node.subscribe(lambda data: None)
        mock_adapter.subscribe.assert_called_once()

        node.unsubscribe()
        mock_adapter.unsubscribe.assert_called_once()


def test_kdb_source_with_init_expr():
    """Test that setup runs init_expr via asyn()."""
    node = KdbSourceNode()
    mock_adapter = MagicMock()
    mock_lib = MagicMock()

    with patch("mirador.nodes.streaming.kdb_source.KDBAdapter", return_value=mock_adapter), \
         patch("mirador.app.get_teide", return_value=mock_lib):
        node.setup({
            "host": "localhost",
            "port": 5001,
            "init_expr": ".u.sub[`trade;`]",
        })
        mock_adapter.asyn.assert_called_once_with(".u.sub[`trade;`]")
