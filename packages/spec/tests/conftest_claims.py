"""The claims plugin: claims whose tables are missing are deselected and listed (6.1 S6).

Nothing is skipped. A claim (`roastery_spec.claims.claim`) whose extract's data folder lacks a
table it needs leaves the run and is printed under "awaiting data" with the tables it waits for.

`conftest.py` imports the hooks into its own namespace: a `pytest_plugins` line is refused in a
conftest that is not the rootdir's, and `--import-mode=importlib` puts no test folder on the path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from roastery_spec.claims import awaiting, claim_of

EXTRACTS = ('tiny', 'month', 'full')
AWAITING = pytest.StashKey[list[tuple[str, tuple[str, ...]]]]()


def _folder(config: pytest.Config, extract: str) -> Path | None:
    """The extract's data folder as conftest.py finds it; None is the baseline."""
    given = config.getoption(f'--{extract}', default=None)
    given = given or os.environ.get(f'ROASTERY_{extract.upper()}_DATA')
    return Path(given) if given else None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    folders = {extract: _folder(config, extract) for extract in EXTRACTS}
    kept: list[pytest.Item] = []
    gone: list[pytest.Item] = []
    waits: list[tuple[str, tuple[str, ...]]] = []
    for item in items:
        found = claim_of(getattr(item, 'function', None))
        missing = awaiting(found.tables, folders[found.extract]) if found else ()
        if missing:
            gone.append(item)
            waits.append((item.name, missing))
        else:
            kept.append(item)
    config.stash[AWAITING] = sorted(waits)
    if gone:
        config.hook.pytest_deselected(items=gone)
        items[:] = kept


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    waits = config.stash.get(AWAITING, [])
    terminalreporter.section('awaiting data')
    if not waits:
        terminalreporter.write_line('none: every claim found its tables')
        return
    for name, missing in waits:
        terminalreporter.write_line(f'{name}: waits for {", ".join(missing)}')
    terminalreporter.write_line(f'{len(waits)} claims awaiting data')
