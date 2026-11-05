"""The web panel and the A/B test visitors of the volume, as pure plans (6.5 V8, V12).

`plan` reads the two target tables as row tuples and fixes who visits when; `facts` turns the
plan into `web_visits` and `web_events` facts once the world has placed the panel's orders.
Every stamp is a whole minute in UTC.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from roastery_sim.outside import WebEvent, WebVisit

FIRST_TEST_DAY = dt.date(2026, 3, 2)
"""Test day 1; day 40 is 10 April 2026."""
PANEL_SIZE = 3600
"""The panel's visit ids run 1 to this; the test visitors' follow."""

START = dt.time(10, 0)
"""The view of a visit, UTC."""
STEPS = (
    ('view', dt.timedelta(0)),
    ('cart', dt.timedelta(minutes=4)),
    ('checkout', dt.timedelta(minutes=6)),
)
ORDER_AFTER = dt.timedelta(minutes=7)
"""A reached-4 visit's order: a minute after its checkout, inside the two-minute window."""
PANEL_SPREAD = 40
"""Minutes between the visits of one panel day: a visit lasts 6, the rule asks for over 30."""
TEST_COUNTRIES = ('FI', 'NO', 'NO', 'NO', 'NO', 'FI', 'SE', 'SE', 'DK', 'FI')
"""A test visitor's country, by `visitor_no % 10` (the mix of tier 3's `deliveries`)."""


@dataclass(frozen=True)
class PanelVisit:
    """A visit of the attributed panel: it has a referrer and no variant."""

    visit_id: int
    visitor_id: str
    visit_date: dt.date
    country: str
    referrer: str
    reached: int
    start: dt.datetime

    @property
    def order_at(self) -> dt.datetime | None:
        """When the world places the visit's order; only a reached-4 visit has one."""
        return self.start + ORDER_AFTER if self.reached == 4 else None


@dataclass(frozen=True)
class TestVisit:
    """The one visit of a test visitor: direct, anonymous, with a variant."""

    __test__ = False  # not a pytest class

    visit_id: int
    visitor_id: str
    visit_date: dt.date
    country: str
    variant: str
    converted: bool
    start: dt.datetime


@dataclass(frozen=True)
class Panel:
    visits: tuple[PanelVisit, ...]
    test: tuple[TestVisit, ...]

    def anchors(self) -> dict[int, dt.datetime]:
        """Reached-4 panel visit id to the moment the world places its order."""
        return {v.visit_id: v.order_at for v in self.visits if v.order_at is not None}


def _at(day: dt.date, minutes: int) -> dt.datetime:
    return dt.datetime.combine(day, START, tzinfo=dt.UTC) + dt.timedelta(minutes=minutes)


def plan(visits: Sequence[tuple], checkout_test: Sequence[tuple], *, seed: int) -> Panel:
    """The panel and the test visitors.

    `visits` rows are (visit_id, visit_date, country, source, reached); `checkout_test` rows
    are (visitor_no, test_day, variant, converted), both in tier3.sql's column order.
    """
    rng = Random(seed)
    by_day: dict[dt.date, list[tuple]] = defaultdict(list)
    for row in sorted(visits):
        by_day[row[1]].append(row)
    panel: list[PanelVisit] = []
    for day in sorted(by_day):
        rows = by_day[day]
        slots = list(range(len(rows)))
        rng.shuffle(slots)
        for (visit_id, _, country, source, reached), slot in zip(rows, slots, strict=True):
            start = _at(day, slot * PANEL_SPREAD)
            if start.date() != day:
                raise ValueError(f'too many panel visits on {day}')
            panel.append(
                PanelVisit(visit_id, f'PV-{visit_id:05d}', day, country, source, reached, start)
            )

    by_test_day: dict[int, list[tuple]] = defaultdict(list)
    for row in sorted(checkout_test):
        by_test_day[row[1]].append(row)
    test: list[TestVisit] = []
    for test_day in sorted(by_test_day):
        rows = by_test_day[test_day]
        day = FIRST_TEST_DAY + dt.timedelta(days=test_day - 1)
        minutes = list(range(len(rows)))
        rng.shuffle(minutes)
        for (visitor_no, _, variant, converted), minute in zip(rows, minutes, strict=True):
            country = TEST_COUNTRIES[visitor_no % 10]
            visit_id = PANEL_SIZE + visitor_no
            visitor = f'TV-{visitor_no:05d}'
            start = _at(day, minute)
            test.append(TestVisit(visit_id, visitor, day, country, variant, bool(converted), start))
    panel.sort(key=lambda v: v.visit_id)
    test.sort(key=lambda v: v.visit_id)
    return Panel(tuple(panel), tuple(test))


def facts(
    panel: Panel, placed: Mapping[int, str]
) -> tuple[tuple[WebVisit, ...], tuple[WebEvent, ...]]:
    """The panel's and the test's `web_visits` and `web_events`.

    `placed` maps a reached-4 panel visit id to the customer who placed its order; that visit's
    events carry the customer. Every other event is anonymous. A panel visit reached 1 to 3
    views, carts and checks out as far as it got; a test visit that converted does all three,
    one that did not only views.
    """
    visits: list[WebVisit] = []
    events: list[WebEvent] = []

    def add(visit_id: int, visitor: str, customer: str | None, start: dt.datetime, steps: int):
        for kind, after in STEPS[:steps]:
            event_id = f'WE-{len(events) + 1:06d}'
            events.append(WebEvent(event_id, visitor, customer, kind, start + after, visit_id))

    for v in panel.visits:
        customer = None
        if v.reached == 4:
            if v.visit_id not in placed:
                raise ValueError(f'visit {v.visit_id} reached 4 but no order was placed')
            customer = placed[v.visit_id]
        visits.append(WebVisit(v.visit_id, v.visitor_id, v.visit_date, v.country, v.referrer, None))
        add(v.visit_id, v.visitor_id, customer, v.start, min(v.reached, 3))
    for t in panel.test:
        visits.append(WebVisit(t.visit_id, t.visitor_id, t.visit_date, t.country, None, t.variant))
        add(t.visit_id, t.visitor_id, None, t.start, 3 if t.converted else 1)
    return tuple(visits), tuple(events)
