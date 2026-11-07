"""The roastery's imports as a graph, pointing inward.

import_graph reads each module of roastery with `ast`, without
running it, and lists who imports whom among its own modules.
Every import counts: one inside a function, or under TYPE_CHECKING,
ties the modules as much as one at the top. An `import roastery`
followed by `roastery.x` is not seen: write `from roastery import
x`.
"""

from __future__ import annotations

import ast
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Self

PACKAGE: Final = 'roastery'
"""The package whose modules the graph holds."""

LAYERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'core': (
            'catalogue',
            'clock',
            'commands',
            'customer',
            'errors',
            'events',
            'ids',
            'money',
            'order',
            'parsing',
            'pipeline',
            'pricing',
            'result',
            'subscription',
            'vat',
        ),
        'ports': ('ports',),
        'vendor': ('provider_sdk',),
        'adapters': (
            'cache',
            'exports',
            'fakes',
            'outbox',
            'provider',
            'repository',
            'resilience',
            'uow',
        ),
        'service': (
            'checkout',
            'customers',
            'fulfilment',
            'listing',
            'payments',
            'reports',
            'stock',
            'storefront',
            'subscriptions',
        ),
        'api': ('api', 'cli', 'idempotency', 'middleware'),
        'bootstrap': ('bootstrap', 'settings'),
        'checks': ('architecture', 'contracts'),
    }
)
"""The modules of each layer, sorted; a module is in one row."""

INWARD: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        'core': ('core',),
        'ports': ('core', 'ports'),
        'vendor': ('vendor',),
        'adapters': ('core', 'ports', 'vendor', 'adapters'),
        'service': ('core', 'ports', 'service'),
        'api': ('core', 'ports', 'service', 'api'),
        'bootstrap': (
            'core',
            'ports',
            'vendor',
            'adapters',
            'service',
            'api',
            'bootstrap',
        ),
        'checks': ('core', 'ports', 'checks'),
    }
)
"""The layers each layer may import: its own and those inside it.

The service and the adapters both stand on the ports, and neither
imports the other. Only adapters and bootstrap see the vendor.
"""


@dataclass(frozen=True)
class ImportEdge:
    """One module importing another, named `importer -> imported`."""

    edge: str
    importer: str
    imported: str

    @classmethod
    def of(cls, importer: str, imported: str) -> Self:
        return cls(f'{importer} -> {imported}', importer, imported)


def imported_by(tree: ast.Module) -> set[str]:
    """The roastery modules a module's code imports, by name."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            found.update(_module(name) for name in names)
        elif isinstance(node, ast.ImportFrom):
            found.update(_modules_from(node))
    found.discard('')
    return found


def _module(name: str) -> str:
    """`roastery.money` is `money`; a name outside it is ''."""
    head, _, rest = name.partition('.')
    return rest if head == PACKAGE else ''


def _modules_from(node: ast.ImportFrom) -> list[str]:
    """The modules of `from roastery.x import y` or `from . import`."""
    if node.level > 1:
        raise ValueError(f'an import above {PACKAGE} at {node.lineno}')
    base = node.module or ''
    if node.level == 1:
        base = f'{PACKAGE}.{base}' if base else PACKAGE
    if base == PACKAGE:
        return [alias.name for alias in node.names]
    return [_module(base)]


def import_graph(package_dir: Path) -> list[ImportEdge]:
    """Every import between roastery's modules, sorted by edge.

    `package_dir` is the folder of roastery. Its modules are read
    in sorted order; __init__.py is left out. Names are module
    names, never paths.
    """
    files = sorted(package_dir.glob('*.py'))
    stems = {file.stem for file in files} - {'__init__'}
    edges: set[ImportEdge] = set()
    for file in files:
        if file.stem not in stems:
            continue
        tree = ast.parse(file.read_text(encoding='utf-8'))
        try:
            found = imported_by(tree)
        except ValueError as error:
            raise ValueError(f'{file.stem}: {error}') from error
        for imported in found:
            if imported != file.stem and imported in stems:
                edges.add(ImportEdge.of(file.stem, imported))
    return sorted(edges, key=lambda e: e.edge)


def unplaced(package_dir: Path) -> list[str]:
    """The modules on disk that no row of LAYERS names, sorted."""
    placed = {name for row in LAYERS.values() for name in row}
    return sorted(
        file.stem
        for file in package_dir.glob('*.py')
        if file.stem != '__init__' and file.stem not in placed
    )


def layer_of(module: str) -> str:
    """The module's layer; raises ValueError when it has none."""
    for layer, names in LAYERS.items():
        if module in names:
            return layer
    raise ValueError(f'no layer for module {module!r}')


@dataclass(frozen=True)
class Violation:
    """An import that points outward, or sideways between layers."""

    edge: str
    importer_layer: str
    imported_layer: str


def check_direction(
    edges: Iterable[ImportEdge],
    allowed: Mapping[str, Collection[str]] = INWARD,
) -> list[Violation]:
    """The edges whose target layer `allowed` does not list, sorted.

    A layer missing from `allowed` may import nothing.
    """
    found: list[Violation] = []
    for edge in edges:
        here = layer_of(edge.importer)
        there = layer_of(edge.imported)
        if there not in allowed.get(here, ()):
            found.append(Violation(edge.edge, here, there))
    return sorted(found, key=lambda v: v.edge)
