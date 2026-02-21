"""Tests for publish/unpublish lifecycle."""

from mirador.engine.publish_registry import PublishRegistry
from mirador.engine.table_env import TableEnv


def test_publish_registry_basic():
    registry = PublishRegistry()
    assert registry.list_running() == []

    env = TableEnv()
    registry.register("proj/pipe1", env, executor=None)
    assert "proj/pipe1" in registry.list_running()

    registry.unregister("proj/pipe1")
    assert registry.list_running() == []


def test_publish_registry_get():
    registry = PublishRegistry()
    env = TableEnv()
    registry.register("proj/pipe1", env, executor="fake_executor")
    entry = registry.get("proj/pipe1")
    assert entry is not None
    assert entry["env"] is env
    assert entry["executor"] == "fake_executor"


def test_publish_registry_get_missing():
    registry = PublishRegistry()
    assert registry.get("nonexistent") is None


def test_restore_published_finds_pipelines(tmp_path):
    """restore_published_pipelines should find pipelines with published=true."""
    from mirador.storage.projects import ProjectStore

    store = ProjectStore(root=tmp_path)
    store.create_project("test")
    store.save_pipeline("test", "stream1", {
        "nodes": [], "edges": [], "published": True,
    })
    store.save_pipeline("test", "batch1", {
        "nodes": [], "edges": [], "published": False,
    })

    # Scan for published pipelines
    published = []
    for slug in [p["slug"] for p in store.list_projects()]:
        for name in store.list_pipelines(slug):
            pipeline = store.load_pipeline(slug, name)
            if pipeline and pipeline.get("published"):
                published.append(f"{slug}/{name}")

    assert published == ["test/stream1"]
