"""Guard for docs/PLAN.md §5b: tool logic stays a pure Python package.

clear_tools may import only the standard library, so it runs and is tested
without an AWS account and Lambda can wrap it unchanged. Adding a third-party
dependency to clear_tools is a deliberate decision: list it in
ALLOWED_THIRD_PARTY.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import clear_tools

ALLOWED_THIRD_PARTY: set[str] = set()

# Runs in a fresh interpreter, so modules already loaded by pytest hide nothing.
PROBE = """
import importlib, json, pkgutil, sys
before = set(sys.modules)
import clear_tools
for module in pkgutil.walk_packages(clear_tools.__path__, "clear_tools."):
    importlib.import_module(module.name)
print(json.dumps(sorted({name.split(".")[0] for name in set(sys.modules) - before})))
"""


def test_clear_tools_imports_only_stdlib():
    src_dir = Path(clear_tools.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(src_dir)}
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr

    loaded = set(json.loads(result.stdout))
    third_party = loaded - set(sys.stdlib_module_names) - {"clear_tools"} - ALLOWED_THIRD_PARTY
    assert not third_party, f"clear_tools imports non-stdlib modules: {sorted(third_party)}"
