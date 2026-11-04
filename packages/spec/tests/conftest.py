"""Data folders for the claims: tiny, month and full, as DuckDB connections.

A data folder holds one `<table>.parquet` per table and a `manifest.json`. Each of the three
extracts comes from, in this order: the option (`--tiny`, `--month`, `--full`), the environment
(`ROASTERY_TINY_DATA`, `ROASTERY_MONTH_DATA`, `ROASTERY_FULL_DATA`), or the baseline, built
once a session.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pytest
from roastery_spec import baseline

from .conftest_claims import pytest_collection_modifyitems, pytest_terminal_summary  # noqa: F401

EXTRACTS = ('tiny', 'month', 'full')


def pytest_addoption(parser: pytest.Parser) -> None:
    for name in EXTRACTS:
        parser.addoption(
            f'--{name}',
            default=None,
            help=f'the data folder the {name} claims run on (env ROASTERY_{name.upper()}_DATA)',
        )


@pytest.fixture(scope='session')
def folders(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The data folder of each extract; the baseline, built once, where none is given."""
    found: dict[str, Path] = {}
    for name in EXTRACTS:
        given = request.config.getoption(f'--{name}', default=None)
        given = given or os.environ.get(f'ROASTERY_{name.upper()}_DATA')
        if given:
            found[name] = Path(given)
    if len(found) < len(EXTRACTS):
        built = tmp_path_factory.mktemp('baseline')
        baseline.build(built)
        for name in EXTRACTS:
            found.setdefault(name, built)
    return found


def manifest_of(folder: Path) -> dict:
    """The parsed `manifest.json` of a data folder."""
    return json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))


def load(folder: Path, reverse: bool = False) -> duckdb.DuckDBPyConnection:
    """A DuckDB in memory holding every table of the folder's manifest.

    With `reverse`, each table is rebuilt last row first (`ORDER BY rowid DESC`), as data-docs'
    `sql._database(reverse=True)` does, so a claim that leans on row order breaks.
    """
    con = duckdb.connect()
    for name in manifest_of(folder)['tables']:
        path = (folder / f'{name}.parquet').as_posix()
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
        if reverse:
            con.execute(f'CREATE TABLE _reversed AS SELECT * FROM {name} ORDER BY rowid DESC')
            con.execute(f'DROP TABLE {name}')
            con.execute(f'ALTER TABLE _reversed RENAME TO {name}')
    return con


@pytest.fixture(scope='session')
def tiny(folders: dict) -> duckdb.DuckDBPyConnection:
    return load(folders['tiny'])


@pytest.fixture(scope='session')
def month(folders: dict) -> duckdb.DuckDBPyConnection:
    return load(folders['month'])


@pytest.fixture(scope='session')
def full(folders: dict) -> duckdb.DuckDBPyConnection:
    return load(folders['full'])


@pytest.fixture(scope='session')
def tiny_reversed(folders: dict) -> duckdb.DuckDBPyConnection:
    return load(folders['tiny'], reverse=True)
