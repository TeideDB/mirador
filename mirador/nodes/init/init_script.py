"""Init script node — runs Python code once during pipeline initialization."""

from typing import Any

from mirador.nodes.base import BaseNode, NodeMeta, NodePort


# Allowlisted builtins for the sandbox
_SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "range": range,
    "int": int, "float": float, "str": str, "list": list, "dict": dict,
    "tuple": tuple, "set": set, "bool": bool,
    "sorted": sorted, "enumerate": enumerate, "zip": zip, "map": map,
    "filter": filter, "abs": abs, "round": round, "print": print,
    "isinstance": isinstance, "type": type,
    "True": True, "False": False, "None": None,
}


class InitScriptNode(BaseNode):
    meta = NodeMeta(
        id="init_script",
        label="Init Script",
        category="init",
        description="Run Python code once at pipeline start to set up tables and state",
        inputs=[NodePort(name="in", description="Input from other init nodes")],
        outputs=[NodePort(name="out", description="Init output")],
        config_schema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "title": "Python Code",
                    "description": "Set 'output' variable with result dict. "
                                   "Available: lib (TeideLib), env (TableEnv), input (upstream data)",
                },
            },
            "required": ["code"],
        },
    )

    def execute(self, inputs: dict[str, Any], config: dict[str, Any], env=None) -> dict[str, Any]:
        from mirador.app import get_teide

        code = config["code"]
        lib = get_teide()

        sandbox = {
            "input": inputs,
            "output": {},
            "lib": lib,
            "env": env,
            "__builtins__": dict(_SAFE_BUILTINS),
        }

        compiled = compile(code, "<init_script>", "exec")
        exec(compiled, sandbox)

        result = sandbox["output"]
        if not isinstance(result, dict):
            raise TypeError(f"Init script 'output' must be a dict, got {type(result).__name__}")
        return result
