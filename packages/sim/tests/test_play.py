"""The play: the script through the two wirings over one store (W1, W4, W8)."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterator

import pytest
from roastery.pipeline import Rows
from roastery_sim.play import Played, play


def _at(day: int, hour: int, minute: int = 0, second: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, second, tzinfo=dt.UTC)


def _dicts(rows: Rows) -> Iterator[dict[str, object]]:
    return (dict(zip(rows.columns, row, strict=True)) for row in rows.rows)


@pytest.fixture(scope='module')
def played() -> Played:
    """The whole play on the memory store, once for the module."""
    return play()


def test_the_whole_play_runs_with_no_failure(played: Played) -> None:
    # play raises PlayStopped after a day with a handler failure, so a result is no failure
    assert played.seed == 0
    assert 'stock_daily' in played.tables
    assert set(played.csv) == {'raw_customers.csv', 'raw_lines.csv'}


def test_the_opening_stock_is_42_and_5() -> None:
    opening = play(until=_at(5, 0))
    on_hand: Counter[object] = Counter()
    for row in _dicts(opening.tables['stock_movements']):
        on_hand[row['product_id']] += row['qty']  # type: ignore[operator]
    assert (on_hand['P-10'], on_hand['P-20']) == (42, 5)


def test_the_refused_batches_wait_and_the_others_go(played: Played) -> None:
    relays = dict(played.relays)
    [e09] = relays[_at(6, 15, 20, 30)].waiting
    assert relays[_at(6, 15, 20, 30)].sent == ()
    assert relays[_at(6, 15, 30)].waiting == (e09,)
    assert relays[_at(6, 15, 30)].sent != ()  # E-10's batch goes past the waiting one
    assert e09 in relays[_at(6, 15, 45)].sent
    [e08] = relays[_at(8, 22)].waiting
    assert relays[_at(8, 22)].sent == ()
    assert relays[_at(9, 19, 45)].waiting == (e08,)
    assert relays[_at(9, 19, 45)].sent != ()  # E-13 and E-14
    assert relays[_at(10, 7)].sent == (e08,)
    assert relays[_at(10, 7)].waiting == ()


# dataset.sql's order_events: (event_id, loaded_at)
LOADED_AT = {
    'E-01': _at(5, 8, 15),
    'E-02': _at(5, 8, 15),
    'E-03': _at(6, 14),
    'E-04': _at(8, 11),
    'E-05': _at(5, 22),
    'E-06': _at(5, 22),
    'E-07': _at(7, 9, 15),
    'E-08': _at(10, 7),
    'E-09': _at(6, 15, 45),
    'E-10': _at(6, 15, 30),
    'E-11': _at(6, 21, 45),
    'E-12': _at(7, 6, 15),
    'E-13': _at(9, 19, 45),
    'E-14': _at(9, 19, 45),
}


def test_each_week_event_is_loaded_once_at_its_moment(played: Played) -> None:
    week = [row for row in _dicts(played.feed) if row['event_id'] in LOADED_AT]
    assert sorted(row['event_id'] for row in week) == sorted(LOADED_AT)  # each once
    assert {row['event_id']: row['loaded_at'] for row in week} == LOADED_AT


def test_the_apps_counts_are_the_datasets(played: Played) -> None:
    counted = {
        (row['product_id'], row['stock_date'], row['counted_at']): row['on_hand']
        for row in _dicts(played.tables['stock_daily'])
        if row['product_id'] in {'P-10', 'P-20'}
    }
    days = range(5, 10)
    expected = {
        **{
            ('P-10', dt.date(2026, 10, day), _at(day, 16)): on_hand
            for day, on_hand in zip(days, (40, 37, 36, 60, 59), strict=True)
        },
        **{('P-20', dt.date(2026, 10, day), _at(day, 16)): 4 for day in days},
    }
    assert counted == expected
    rows = [r for r in _dicts(played.tables['stock_daily']) if r['product_id'] in {'P-10', 'P-20'}]
    assert len(rows) == len(expected)  # one row per product and day
