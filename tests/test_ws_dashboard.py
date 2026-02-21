"""Tests for dashboard WebSocket endpoint."""

import pytest
from starlette.testclient import TestClient

from mirador.app import app, get_publish_registry
from mirador.engine.table_env import TableEnv


@pytest.fixture
def client():
    return TestClient(app)


def test_ws_dashboard_subscribe_and_fetch(init_teide, client):
    """Test basic subscribe -> fetch flow."""
    registry = get_publish_registry()
    env = TableEnv()
    env.set("test_table", {
        "rows": [{"x": 1}, {"x": 2}, {"x": 3}],
        "columns": ["x"],
        "total": 3,
    })
    registry.register("proj/pipe1", env, executor=None)

    try:
        with client.websocket_connect("/ws/dashboard/proj/pipe1") as ws:
            ws.send_json({
                "action": "subscribe",
                "widget_id": "w1",
                "table": "test_table",
                "page": 0,
                "page_size": 50,
            })
            response = ws.receive_json()
            assert response["event"] == "subscribed"

            ws.send_json({"action": "fetch", "widget_id": "w1"})
            response = ws.receive_json()
            assert response["event"] == "page"
            assert response["widget_id"] == "w1"
            assert len(response["rows"]) == 3
    finally:
        registry.unregister("proj/pipe1")


def test_ws_dashboard_pipeline_not_found(init_teide, client):
    """Test connecting to a non-existent pipeline."""
    with client.websocket_connect("/ws/dashboard/no/such/pipe") as ws:
        response = ws.receive_json()
        assert response["event"] == "error"
        assert "not running" in response["error"]


def test_ws_dashboard_fetch_without_subscribe(init_teide, client):
    """Test fetching before subscribing returns error."""
    registry = get_publish_registry()
    env = TableEnv()
    env.set("test_table", {
        "rows": [{"x": 1}],
        "columns": ["x"],
        "total": 1,
    })
    registry.register("proj/pipe2", env, executor=None)

    try:
        with client.websocket_connect("/ws/dashboard/proj/pipe2") as ws:
            ws.send_json({"action": "fetch", "widget_id": "w_unsubscribed"})
            response = ws.receive_json()
            assert response["event"] == "error"
            assert "not subscribed" in response["error"]
    finally:
        registry.unregister("proj/pipe2")


def test_ws_dashboard_fetch_missing_table(init_teide, client):
    """Test fetching a table that doesn't exist in the env."""
    registry = get_publish_registry()
    env = TableEnv()
    registry.register("proj/pipe3", env, executor=None)

    try:
        with client.websocket_connect("/ws/dashboard/proj/pipe3") as ws:
            ws.send_json({
                "action": "subscribe",
                "widget_id": "w1",
                "table": "nonexistent_table",
            })
            response = ws.receive_json()
            assert response["event"] == "subscribed"

            ws.send_json({"action": "fetch", "widget_id": "w1"})
            response = ws.receive_json()
            assert response["event"] == "error"
            assert "not found" in response["error"]
    finally:
        registry.unregister("proj/pipe3")


def test_ws_dashboard_pagination(init_teide, client):
    """Test pagination of table data."""
    registry = get_publish_registry()
    env = TableEnv()
    rows = [{"x": i} for i in range(10)]
    env.set("big_table", {
        "rows": rows,
        "columns": ["x"],
        "total": 10,
    })
    registry.register("proj/pipe4", env, executor=None)

    try:
        with client.websocket_connect("/ws/dashboard/proj/pipe4") as ws:
            ws.send_json({
                "action": "subscribe",
                "widget_id": "w1",
                "table": "big_table",
                "page": 0,
                "page_size": 3,
            })
            response = ws.receive_json()
            assert response["event"] == "subscribed"

            ws.send_json({"action": "fetch", "widget_id": "w1"})
            response = ws.receive_json()
            assert response["event"] == "page"
            assert len(response["rows"]) == 3
            assert response["total"] == 10
            assert response["rows"][0]["x"] == 0
            assert response["rows"][2]["x"] == 2
    finally:
        registry.unregister("proj/pipe4")
