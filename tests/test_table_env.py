from mirador.engine.table_env import TableEnv


def test_set_and_get():
    env = TableEnv()
    env.set("trades", {"fake": "table"})
    assert env.get("trades") == {"fake": "table"}


def test_get_missing_raises():
    env = TableEnv()
    try:
        env.get("missing")
        assert False, "Expected KeyError"
    except KeyError:
        pass


def test_drop():
    env = TableEnv()
    env.set("trades", {"fake": "table"})
    env.drop("trades")
    assert "trades" not in env.list()


def test_list():
    env = TableEnv()
    env.set("a", 1)
    env.set("b", 2)
    assert sorted(env.list()) == ["a", "b"]


def test_clear():
    env = TableEnv()
    env.set("a", 1)
    env.set("b", 2)
    env.clear()
    assert env.list() == []


def test_env_passthrough_in_execute():
    """Verify BaseNode.execute() accepts env kwarg without error."""
    from mirador.nodes.base import BaseNode, NodeMeta, NodePort

    class DummyNode(BaseNode):
        meta = NodeMeta(
            id="dummy", label="Dummy", category="generic",
            inputs=[], outputs=[NodePort(name="out", description="test")],
        )

        def execute(self, inputs, config, env=None):
            return {"env_present": env is not None}

    node = DummyNode()
    result = node.execute({}, {}, env="fake_env")
    assert result["env_present"] is True

    # Also works without env (backward compatible)
    result2 = node.execute({}, {})
    assert result2["env_present"] is False
