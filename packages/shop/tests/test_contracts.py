"""The two stores keep the same promises (ADR 0015, A2).

Every suite of `roastery.contracts` runs on the memory store and on
sqlite over `:memory:`. Each store must pass, and the two must give
the same rows of `Check`: that equality is what makes a test that
uses the memory store tell the truth about sqlite.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager

import pytest

from roastery.contracts import (
    Check,
    check_customers,
    check_orders,
    check_outbox,
    check_reads,
    check_source,
    check_stock,
    check_unit_of_work,
)
from roastery.ports import Source, UnitOfWork

type Build = Callable[[Source], UnitOfWork]
"""A new, empty store's unit of work, stamping the given source."""

type Suite = Callable[[Callable[[], UnitOfWork]], list[Check]]

SUITES: Mapping[str, Suite] = {
    'orders': check_orders,
    'customers': check_customers,
    'outbox': check_outbox,
    'unit_of_work': check_unit_of_work,
    'stock': check_stock,
    'source': check_source,
    'reads': check_reads,
}

SOURCES: tuple[Source, ...] = ('scripted', 'simulator', 'visitor')


class _Clock:
    """A moment that never moves: the stores only need it for the
    price cache, which these suites do not touch."""

    def now(self) -> dt.datetime:
        return dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC)


@contextmanager
def _builders() -> Iterator[Mapping[str, Build]]:
    """Each store's builder; every sqlite connection is closed
    when the block ends, so no file or memory is left open."""
    from roastery.bootstrap import memory_store, sqlite_store

    connections: list[sqlite3.Connection] = []

    def memory(source: Source) -> UnitOfWork:
        store = memory_store(clock=_Clock(), price_ttl=60)
        return store.unit_of_work(source)

    def sqlite(source: Source) -> UnitOfWork:
        connection = sqlite3.connect(':memory:')
        connections.append(connection)
        store = sqlite_store(connection, clock=_Clock(), price_ttl=60)
        return store.unit_of_work(source)

    try:
        yield {'memory': memory, 'sqlite': sqlite}
    finally:
        for connection in connections:
            connection.close()


@pytest.fixture
def builders() -> Iterator[Mapping[str, Build]]:
    with _builders() as built:
        yield built


@pytest.fixture(params=['memory', 'sqlite'], ids=['memory', 'sqlite'])
def build_uow(
    request: pytest.FixtureRequest,
    builders: Mapping[str, Build],
) -> Build:
    return builders[request.param]


@pytest.fixture
def make_uow(build_uow: Build) -> Callable[[], UnitOfWork]:
    """A new store per call, as the suites ask for it."""
    return lambda: build_uow('simulator')


def _failed(checks: list[Check]) -> list[str]:
    return [f'{c.name}: {c.detail}' for c in checks if not c.passed]


@pytest.mark.parametrize('suite', SUITES)
def test_every_check_of_a_suite_passes(
    suite: str, make_uow: Callable[[], UnitOfWork]
) -> None:
    checks = SUITES[suite](make_uow)
    assert checks
    assert _failed(checks) == []


@pytest.mark.parametrize('source', SOURCES)
def test_rows_follow_the_source_of_their_unit_of_work(
    source: Source, build_uow: Build
) -> None:
    checks = check_source(lambda: build_uow(source))
    assert _failed(checks) == []


def test_both_stores_give_the_same_checks(
    builders: Mapping[str, Build],
) -> None:
    for name, suite in SUITES.items():
        memory = suite(lambda: builders['memory']('simulator'))
        sqlite = suite(lambda: builders['sqlite']('simulator'))
        assert _failed(memory) == [], name
        assert _failed(sqlite) == [], name
        assert memory == sqlite, name
