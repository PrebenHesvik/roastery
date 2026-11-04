"""The simulator imports from the shop only contract B's names (W3, C27).

Contract B is read where it is written, at test time: every name `contract_b.txt` pins, every
name the python block of `docs/architecture.md` section 5 imports from `roastery`, and `Rows`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import roastery_sim

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / 'packages' / 'shop' / 'tests' / 'contract_b.txt'
ARCHITECTURE = ROOT / 'docs' / 'architecture.md'
PINNED = re.compile(r'^(\w+)(?=\.|\(| =)')


def _shop(module: str | None) -> bool:
    return module is not None and (module == 'roastery' or module.startswith('roastery.'))


def _section_five_block() -> str:
    """The first fenced python block after the heading of section 5."""
    text = ARCHITECTURE.read_text(encoding='utf-8')
    found = re.search(r'^## 5\. .*?^```python\n(.*?)^```', text, re.M | re.S)
    assert found, 'no python block in section 5 of architecture.md'
    return found.group(1)


def _contract_b() -> frozenset[str]:
    names = set()
    for line in SNAPSHOT.read_text(encoding='utf-8').splitlines():
        if line.strip():
            pinned = PINNED.match(line)
            assert pinned, f'contract_b.txt: no name on {line!r}'
            names.add(pinned.group(1))
    for node in ast.walk(ast.parse(_section_five_block())):
        if isinstance(node, ast.ImportFrom) and _shop(node.module):
            names.update(alias.name for alias in node.names)
    return frozenset(names | {'Rows'})


def test_the_simulator_imports_only_contract_b() -> None:
    allowed = _contract_b()
    package = Path(roastery_sim.__file__).parent
    modules = sorted(package.rglob('*.py'))
    assert modules
    outside = []
    for path in modules:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                outside += [
                    (path.name, node.lineno, f'import {alias.name}')
                    for alias in node.names
                    if _shop(alias.name)
                ]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and _shop(node.module):
                outside += [
                    (path.name, node.lineno, f'{node.module}.{alias.name}')
                    for alias in node.names
                    if alias.name not in allowed
                ]
    assert outside == []
