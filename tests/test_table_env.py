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
