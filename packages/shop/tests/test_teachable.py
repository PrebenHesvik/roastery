"""The code stays teachable: ADR 0015's rules, read with `ast`.

No module state, no wall clock, no unseeded randomness, and every
listing sorted. Each failure names the module and the line.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import roastery

PACKAGE_DIR = Path(roastery.__file__).parent

ALLOWED_CALLS = frozenset(
    {'MappingProxyType', 'NewType', 'frozenset', 'tuple', 'Decimal'}
    | {'TypeVar'}
)
DISPLAYS = (
    ast.List,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
)
WALL_CLOCK = frozenset(
    {
        'datetime.datetime.now',
        'datetime.datetime.utcnow',
        'datetime.datetime.today',
        'datetime.date.today',
        'time.time',
        'time.time_ns',
        'time.monotonic',
        'time.perf_counter',
    }
)
UNSEEDED = frozenset({'uuid.uuid1', 'uuid.uuid4', 'os.urandom'})


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Each imported name, with the dotted name it stands for."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    found[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                key = alias.asname or alias.name
                found[key] = f'{node.module}.{alias.name}'
    return found


def _dotted(node: ast.expr, aliases: dict[str, str]) -> str:
    """`dt.datetime.now` as `datetime.datetime.now`; '' if no name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ''
    parts.append(aliases.get(node.id, node.id))
    return '.'.join(reversed(parts))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ''


def _module_state(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if isinstance(value, DISPLAYS):
            found.append((node.lineno, 'module state: a mutable value'))
        elif isinstance(value, ast.Call):
            if _call_name(value) not in ALLOWED_CALLS:
                found.append((node.lineno, 'module state: a call'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            found.append((node.lineno, 'module state: global'))
    return found


def _secrets(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or '']
        else:
            continue
        if any(name.split('.')[0] == 'secrets' for name in names):
            found.append((node.lineno, 'unseeded random: secrets'))
    return found


def _clock_and_random(tree: ast.Module) -> list[tuple[int, str]]:
    found = _secrets(tree)
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            bare = not node.args and not node.keywords
            if bare and _dotted(node.func, aliases) == 'random.Random':
                found.append((node.lineno, 'unseeded random: Random()'))
        if not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        name = _dotted(node, aliases)
        if name in WALL_CLOCK:
            found.append((node.lineno, f'wall clock: {name}'))
        elif name in UNSEEDED or (
            name.startswith('random.') and name != 'random.Random'
        ):
            found.append((node.lineno, f'unseeded random: {name}'))
    return found


def _text(node: ast.AST) -> str:
    """The literal text of a string or an f-string; else ''."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(_text(part) for part in node.values)
    return ''


def _unsorted_listings(tree: ast.Module) -> list[tuple[int, str]]:
    one_row: set[int] = set()
    for node in ast.walk(tree):
        func = node.func if isinstance(node, ast.Call) else None
        if isinstance(func, ast.Attribute) and func.attr == 'fetchone':
            one_row.update(id(sub) for sub in ast.walk(func.value))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        text = _text(node)
        if not text.lstrip().startswith('SELECT'):
            continue
        if 'ORDER BY' not in text.upper() and id(node) not in one_row:
            found.append((node.lineno, 'listing: no ORDER BY'))
    return found


def breaches(source: str) -> list[tuple[int, str]]:
    """Every rule `source` breaks, as (line, rule), sorted."""
    tree = ast.parse(source)
    found = _module_state(tree)
    found += _clock_and_random(tree)
    found += _unsorted_listings(tree)
    return sorted(set(found))


def test_the_package_is_teachable() -> None:
    found = [
        f'{file.stem}:{line}: {rule}'
        for file in sorted(PACKAGE_DIR.glob('*.py'))
        for line, rule in breaches(file.read_text(encoding='utf-8'))
    ]
    assert found == []


BITES = [
    ('CACHE = []', 'module state'),
    ('CACHE = {}', 'module state'),
    ('SEEN = {n for n in range(3)}', 'module state'),
    ('ROWS = list(range(3))', 'module state'),
    ('def f():\n    global n\n    n = 1', 'module state'),
    (
        'import datetime as dt\ndef f():\n    return dt.datetime.now()',
        'wall clock',
    ),
    (
        'from datetime import datetime as D\n'
        'def f():\n    return D.utcnow()',
        'wall clock',
    ),
    (
        'from datetime import date\ndef f():\n    return date.today()',
        'wall clock',
    ),
    ('import time\ndef f():\n    return time.time()', 'wall clock'),
    (
        'import time as t\ndef f():\n    return t.perf_counter()',
        'wall clock',
    ),
    (
        'import random\ndef f():\n    return random.choice([1])',
        'unseeded random',
    ),
    (
        'import random\ndef f():\n    return random.Random()',
        'unseeded random',
    ),
    (
        'import uuid\ndef f():\n    return uuid.uuid4()',
        'unseeded random',
    ),
    (
        'import os\ndef f():\n    return os.urandom(4)',
        'unseeded random',
    ),
    ('import secrets', 'unseeded random'),
    ('Q = "SELECT id FROM t"', 'listing'),
    ('db.execute("SELECT id FROM t").fetchall()', 'listing'),
]
FINE = [
    'from decimal import Decimal\nTAX: Final = Decimal("0.25")',
    'KINDS: Final = frozenset({"a", "b"})',
    'ROWS: Final = ("a", "b")',
    'from types import MappingProxyType\nM = MappingProxyType({})',
    'import random\ndef f():\n    return random.Random(7)',
    'Q = "SELECT id FROM t ORDER BY id"',
    'db.execute("SELECT count(*) FROM t").fetchone()',
    'def f():\n    return [1, 2]',
]


@pytest.mark.parametrize(('source', 'rule'), BITES)
def test_each_rule_bites(source: str, rule: str) -> None:
    found = breaches(source)
    assert found
    assert all(text.startswith(rule) for _, text in found)


@pytest.mark.parametrize('source', FINE)
def test_allowed_code_passes(source: str) -> None:
    assert breaches(source) == []
