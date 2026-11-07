"""The layers hold: imports point inward, every file has a row."""

from __future__ import annotations

from pathlib import Path

import roastery
from roastery.architecture import (
    LAYERS,
    ImportEdge,
    Violation,
    check_direction,
    import_graph,
    unplaced,
)

PACKAGE_DIR = Path(roastery.__file__).parent

# Modules named in LAYERS and not built yet.
AWAITING = ('cli',)


def test_imports_point_inward() -> None:
    assert check_direction(import_graph(PACKAGE_DIR)) == []


def test_every_file_has_a_row() -> None:
    assert unplaced(PACKAGE_DIR) == []


def test_no_module_is_in_two_rows() -> None:
    names = [name for row in LAYERS.values() for name in row]
    assert sorted(names) == sorted(set(names))


def test_only_the_awaiting_modules_have_no_file() -> None:
    names = {name for row in LAYERS.values() for name in row}
    on_disk = {file.stem for file in PACKAGE_DIR.glob('*.py')}
    assert sorted(names - on_disk) == list(AWAITING)
    assert list(AWAITING) == sorted(AWAITING)


def test_the_check_bites() -> None:
    edges = [
        ImportEdge.of('pricing', 'repository'),
        ImportEdge.of('checkout', 'ports'),
        ImportEdge.of('checkout', 'repository'),
    ]
    assert check_direction(edges) == [
        Violation('checkout -> repository', 'service', 'adapters'),
        Violation('pricing -> repository', 'core', 'adapters'),
    ]
