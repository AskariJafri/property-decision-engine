"""ADR 0001 Decision 5, enforced by the build rather than by review.

Engines are pure functions over value objects. The moment one of them imports a
repository or a provider, the financial logic stops being testable without a
database and the reproducibility guarantee quietly dies. So the rule is checked
mechanically, on every commit, by walking the imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_FOR_ENGINES = ("app.services", "app.repositories", "app.providers", "app.ai", "app.api")
ENGINES = Path(__file__).resolve().parents[2] / "app" / "engines"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_engines_do_not_import_io_layers():
    offences: list[str] = []
    for path in ENGINES.rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_FOR_ENGINES):
                offences.append(f"{path.relative_to(ENGINES.parent)} imports {imported}")
    assert not offences, "engines must stay pure:\n" + "\n".join(offences)


def test_engines_do_not_reach_for_the_network_or_a_clock_that_changes_results():
    # datetime is fine for timestamps in a trace; httpx and sqlalchemy are not fine at all.
    banned = {"httpx", "requests", "sqlalchemy", "asyncpg", "openai", "anthropic"}
    offences: list[str] = []
    for path in ENGINES.rglob("*.py"):
        for imported in _imports(path):
            if imported.split(".")[0] in banned:
                offences.append(f"{path.relative_to(ENGINES.parent)} imports {imported}")
    assert not offences, "engines must not perform I/O:\n" + "\n".join(offences)
