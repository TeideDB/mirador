# tests/test_init_script.py
"""Tests for the init_script node."""

from mirador.engine.table_env import TableEnv


def test_init_script_sets_env(init_teide):
    from mirador.nodes.init.init_script import InitScriptNode

    env = TableEnv()
    node = InitScriptNode()
    result = node.execute({}, {
        "code": "env.set('greeting', 'hello')\noutput = {'done': True}"
    }, env=env)

    assert result["done"] is True
    assert env.get("greeting") == "hello"


def test_init_script_has_teide_access(init_teide):
    from mirador.nodes.init.init_script import InitScriptNode

    env = TableEnv()
    node = InitScriptNode()
    result = node.execute({}, {
        "code": "output = {'has_lib': lib is not None}"
    }, env=env)

    assert result["has_lib"] is True


def test_init_script_meta():
    from mirador.nodes.init.init_script import InitScriptNode

    assert InitScriptNode.meta.category == "init"
    assert InitScriptNode.meta.id == "init_script"
