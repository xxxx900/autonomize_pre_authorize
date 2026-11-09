"""Structural rules for the codebase, checked on the source itself."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Services holds live clients and stores; it is wiring, so it cannot live in the no-I/O domain.
WIRING_CONTAINERS = {"Services"}
SOURCE_DIRS = ("app", "agent", "mcp_server", "eval", "scripts", "tests")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def nested_functions(path: Path) -> list[str]:
    """`file:line name` for every def that sits inside another def."""
    found = []
    for outer in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(outer, FUNCTIONS):
            found += [
                f"{path.relative_to(ROOT)}:{inner.lineno} {inner.name} in {outer.name}"
                for inner in ast.walk(outer)
                if isinstance(inner, FUNCTIONS) and inner is not outer
            ]
    return found


def test_no_function_is_defined_inside_another_function():
    files = [p for d in SOURCE_DIRS for p in sorted((ROOT / d).rglob("*.py"))]
    assert files
    assert [hit for p in files for hit in nested_functions(p)] == []


def test_every_function_and_class_outside_tests_has_a_docstring():
    missing = [
        f"{path.relative_to(ROOT)}:{node.lineno} {node.name}"
        for d in SOURCE_DIRS
        if d != "tests"
        for path in sorted((ROOT / d).rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (*FUNCTIONS, ast.ClassDef)) and not ast.get_docstring(node)
    ]
    assert missing == []


def is_data_type(node: ast.stmt) -> bool:
    """A frozen model, an enum, or a dataclass that holds only data fields."""
    if not isinstance(node, ast.ClassDef) or node.name in WIRING_CONTAINERS:
        return False
    bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
    decorators = ast.unparse(node.decorator_list) if node.decorator_list else ""
    methods = [n for n in node.body if isinstance(n, FUNCTIONS)]
    return bool(bases & {"Frozen", "StrEnum"}) or ("dataclass" in decorators and not methods)


def test_every_model_and_enum_lives_in_the_domain_package():
    allowed = {ROOT / "app" / "domain"}
    offenders = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        if path.parent in allowed:
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if is_data_type(node):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert offenders == []
