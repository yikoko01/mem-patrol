"""M0 hard constraints: no host/DB/network deps, no absolute production paths."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_IMPORT_ROOTS = {
    "astrbot",
    "requests",
    "httpx",
    "openai",
    "urllib",
    "socket",
    "http",
}
POLICY_FORBIDDEN_IMPORT_ROOTS = FORBIDDEN_IMPORT_ROOTS | {"sqlite3"}
IO_BUILTINS = {"open", "eval", "exec", "compile"}
ABSOLUTE_PREFIXES = ("/root", "/sdcard")


def python_files():
    return sorted(SRC.rglob("*.py"))


def docstring_constant_ids(tree):
    """Ids of Constant nodes that are docstrings (docs may mention production paths)."""
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def test_no_forbidden_imports():
    offenders = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                root = module.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    offenders.append((path.name, module))
    assert not offenders, offenders


def test_policy_has_no_io_calls_or_absolute_paths():
    offenders = []
    for path in sorted((SRC / "memorix" / "policy").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in POLICY_FORBIDDEN_IMPORT_ROOTS:
                        offenders.append((path.name, "forbidden-import", alias.name))
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in POLICY_FORBIDDEN_IMPORT_ROOTS:
                    offenders.append((path.name, "forbidden-import", node.module))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in IO_BUILTINS
            ):
                offenders.append((path.name, "io-call", node.func.id))
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value.startswith(ABSOLUTE_PREFIXES)
            ):
                offenders.append((path.name, "absolute-path", node.value[:40]))
    assert not offenders, offenders


def test_imports_under_isolated_python():
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import memorix;"
        "from memorix.policy import audit, consolidation, decay, finish_gate, intents, orphan, senders, timeparse;"
        "from memorix import cli, config, diagnose, store, state;"
        "from memorix import gatekeep, retrieval;"
        "print(memorix.__version__)"
    ) % str(SRC)
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    from memorix import __version__

    assert completed.stdout.strip() == __version__


def test_no_absolute_production_paths_in_code():
    offenders = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = docstring_constant_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value.startswith(ABSOLUTE_PREFIXES)
            ):
                offenders.append((path.name, node.value[:40]))
    assert not offenders, offenders
