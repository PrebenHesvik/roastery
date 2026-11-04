"""Fixtures the tests of the stores share (A21).

`store` runs a test on the memory store and on sqlite over
`:memory:`; the connection is closed when the test ends, so no
database is left open.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator

import pytest

from roastery.fakes import FakeClock
from roastery.ports import Store
from roastery.repository import create_tables
from roastery.uow import InMemoryStore, SqliteStore

PRICE_TTL = 60


@pytest.fixture
def clock() -> FakeClock:
    """A clock that moves only when the test moves it."""
    return FakeClock(dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC))


@pytest.fixture(params=['memory', 'sqlite'], ids=['memory', 'sqlite'])
def store(
    request: pytest.FixtureRequest, clock: FakeClock
) -> Iterator[Store]:
    """A new, empty store: the memory one, then the sqlite one."""
    if request.param == 'memory':
        yield InMemoryStore(clock=clock, price_ttl=PRICE_TTL)
        return
    connection = sqlite3.connect(':memory:')
    try:
        create_tables(connection)
        yield SqliteStore(connection, clock=clock, price_ttl=PRICE_TTL)
    finally:
        connection.close()
