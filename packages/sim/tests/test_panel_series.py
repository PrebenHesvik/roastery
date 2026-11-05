"""The panel and the outside series: the counts, the rules and the equality with `shop_days`."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pytest
from roastery_sim import panel, series
from roastery_sim.script import FX
from roastery_spec import baseline


@pytest.fixture(scope='module')
def targets():
    text = ''.join(baseline._text(f'{name}.sql') for name in ('dataset', 'tier3'))
    con = baseline.database(baseline.tables(text))
    return {
        name: con.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall()
        for name in ('visits', 'checkout_test', 'shop_days')
    }


@pytest.fixture(scope='module')
def planned(targets):
    return panel.plan(targets['visits'], targets['checkout_test'], seed=7)


def _placed(planned):
    return {vid: f'C-{vid}' for vid in planned.anchors()}


def test_counts_and_kinds(planned) -> None:
    visits, events = panel.facts(planned, _placed(planned))
    assert [v.visit_id for v in planned.visits] == list(range(1, 3601))
    assert len(planned.test) == 4000
    assert planned.test[0].visit_id == 3601
    days = {t.visit_date for t in planned.test}
    assert (len(days), min(days), max(days)) == (40, dt.date(2026, 3, 2), dt.date(2026, 4, 10))
    panel_rows, test_rows = visits[:3600], visits[3600:]
    assert all(v.variant is None and v.referrer for v in panel_rows)
    assert all(v.referrer is None and v.variant in ('A', 'B') for v in test_rows)
    assert all(e.visit_id is not None and e.event_at.second == 0 for e in events)
    reached4 = {v.visit_id for v in planned.visits if v.reached == 4}
    assert {e.visit_id for e in events if e.customer_id} == reached4


def test_anchor_order_lands_within_two_minutes_of_the_checkout(planned) -> None:
    _, events = panel.facts(planned, _placed(planned))
    checkout = {e.visit_id: e.event_at for e in events if e.event == 'checkout'}
    for visit_id, at in planned.anchors().items():
        assert dt.timedelta(0) <= at - checkout[visit_id] <= dt.timedelta(minutes=2)


def test_no_two_visits_of_a_visitor_are_within_30_minutes(planned) -> None:
    visits, events = panel.facts(planned, _placed(planned))
    assert len({e.event_id for e in events}) == len(events)
    spans: dict[str, list[tuple[dt.datetime, dt.datetime, int]]] = defaultdict(list)
    for e in events:
        spans[e.visitor_id].append((e.event_at, e.event_at, e.visit_id))
    for stamps in spans.values():
        stamps.sort()
        for (_, before, a), (after, _, b) in zip(stamps, stamps[1:], strict=False):
            assert a == b or after - before > dt.timedelta(minutes=30)
    assert {v.visit_id for v in visits} == {e.visit_id for e in events}
    # a visit's own events stay inside the rule too
    for v in planned.visits[:50]:
        mine = [e.event_at for e in events if e.visit_id == v.visit_id]
        assert all(b - a <= dt.timedelta(minutes=30) for a, b in zip(mine, mine[1:], strict=False))


def test_series_rebuild_shop_days_on_its_window(targets) -> None:
    rain = {w.shop_date: w.rain_mm for w in series.weather()}
    doors = {d.shop_date: d.walk_ins for d in series.door_counts()}
    till = {t.shop_date: t.receipts for t in series.till_day_totals()}
    rebuilt = [(day, rain[day], doors[day], till[day]) for day, *_ in targets['shop_days']]
    assert rebuilt == targets['shop_days']
    assert min(rain) == dt.date(2024, 1, 1) and max(rain) == dt.date(2026, 10, 31)
    assert max(till) == dt.date(2026, 10, 5)
    assert min(rain.values()) >= 0


def test_fx_keeps_the_scripts_rows_and_the_walk_ins_follow_the_door(targets) -> None:
    rows = series.fx()
    quiet = [r for r in rows if dt.date(2026, 10, 2) <= r.rate_date <= dt.date(2026, 10, 7)]
    assert sorted(quiet, key=lambda r: (r.currency, r.rate_date)) == sorted(
        FX, key=lambda r: (r.currency, r.rate_date)
    )
    assert all(r.rate_date.weekday() < 5 for r in rows)
    doors = {d.shop_date: d.walk_ins for d in series.door_counts()}
    per_day: dict[dt.date, int] = defaultdict(int)
    receipts = series.walk_in_receipts(seed=3)
    for r in receipts:
        assert r.member_no is None and r.sold_at.date().weekday() != 6
        per_day[r.sold_at.date()] += 1
    assert min(per_day) == dt.date(2026, 10, 10) and max(per_day) == dt.date(2026, 10, 31)
    assert all(count <= doors[day] for day, count in per_day.items())
    assert len({r.receipt_id for r in receipts}) == len(receipts)


def test_same_seed_gives_equal_output(targets) -> None:
    def run(seed: int):
        p = panel.plan(targets['visits'], targets['checkout_test'], seed=seed)
        return p, panel.facts(p, _placed(p)), series.walk_in_receipts(seed=seed)

    assert run(5) == run(5)
    assert run(5) != run(6)
