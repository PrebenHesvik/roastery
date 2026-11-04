"""The play: the script through the two wirings over one store (W1, W4, W8)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from roastery.pipeline import Rows
from roastery_sim.build import build, write
from roastery_sim.play import Played, PlayStopped, play


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


class _RaisingNotifier:
    """A Notifier whose `send` fails,."""

    def __init__(self) -> None:
        self.sends = 0

    def send(self, to: object, *, subject: str, body: str) -> None:
        self.sends += 1
        raise RuntimeError('mail is down')


def _hashes(root: Path) -> dict[str, str]:
    """Each file under root, by relative path, with its sha256."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


def test_the_same_seed_gives_the_same_bytes(tmp_path: Path) -> None:
    for name in ('one', 'two'):
        write(build(seed=0, until=None, store='memory'), tmp_path / name, seed=0, shop_version='t')
    one, two = _hashes(tmp_path / 'one'), _hashes(tmp_path / 'two')
    assert one == two
    assert 'tiny.sql' in one
    assert 'data/manifest.json' in one
    assert any(name.endswith('.parquet') for name in one)
    assert {n for n in one if n.startswith('landing/')} == {
        'landing/raw_customers.csv',
        'landing/raw_lines.csv',
    }


def test_the_sqlite_store_gives_the_memory_stores_bytes() -> None:
    memory = build(seed=0, until=None, store='memory')
    sqlite = build(seed=0, until=None, store='sqlite')
    assert sqlite.text == memory.text
    assert sqlite.defects == memory.defects


def test_a_failing_handler_stops_the_play_on_the_first_confirmation() -> None:
    notifier = _RaisingNotifier()
    with pytest.raises(PlayStopped) as stopped:
        play(notifier=notifier)
    assert stopped.value.day == dt.date(2025, 11, 12)
    assert stopped.value.failures
    assert all('confirm' in failure.handler for failure in stopped.value.failures)


SHA_FILE = Path(__file__).with_name('tiny.sha256')


def test_the_bytes_are_those_committed(tmp_path: Path) -> None:
    built = build(seed=0, until=None, store='memory')
    write(built, tmp_path, seed=0, shop_version='sha-gate')
    got = {
        'tiny': hashlib.sha256(built.text.encode('utf-8')).hexdigest(),
        'manifest': hashlib.sha256((tmp_path / 'data' / 'manifest.json').read_bytes()).hexdigest(),
    }
    first, second = SHA_FILE.read_text(encoding='utf-8').splitlines()
    committed = {'tiny': first, 'manifest': second.removeprefix('manifest ')}
    assert got == committed, (
        f'tiny.sql or manifest.json changed: now tiny {got["tiny"]} and manifest '
        f'{got["manifest"]}. If this is on purpose, rewrite tests/tiny.sha256 with the first as '
        'line 1 and "manifest <hex>" as line 2 (LF).'
    )


def test_a_manifest_says_where_a_play_stopped(tmp_path: Path) -> None:
    whole = build(seed=0, until=None, store='memory')
    write(whole, tmp_path / 'whole', seed=0, shop_version='t')
    stop = _at(5, 0)
    write(
        build(seed=0, until=stop, store='memory'),
        tmp_path / 'cut',
        seed=0,
        shop_version='t',
        until=stop,
    )
    kept = [
        json.loads((tmp_path / n / 'data' / 'manifest.json').read_text()) for n in ('whole', 'cut')
    ]
    assert kept[0]['until'] is None
    assert kept[1]['until'] == '2026-10-05T00:00:00+00:00'
    keys = list(kept[0])
    assert keys.index('until') == keys.index('seed') + 1
