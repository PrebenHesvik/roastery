"""The volume's world (6.5, U3): the quiet window, feasibility on the real targets, V6's 13."""

from __future__ import annotations

import datetime as dt

import pytest
from roastery.ids import OrderId
from roastery_sim import script, targets, world
from roastery_sim.script import (
    Deliver,
    NightlyExtract,
    Pay,
    Place,
    Register,
    Roast,
    Ship,
    Stocktake,
    Subscribe,
)

MISFITS = (39, 117, 336, 348, 378, 399, 423, 468, 489, 501, 531, 579, 594)
"""The lesson web orders over their day's P-11 quota, by the lead's fit (V6)."""


@pytest.fixture(scope='module')
def built() -> tuple[targets.Targets, world.Volume]:
    found = targets.build()
    return found, world.build(found, seed=0)


def test_feasibility_passes_on_the_real_targets():
    report = world.feasibility(targets.build())
    assert report.misfits == MISFITS
    assert all(line for line in report.lines())


def test_the_13_misfit_lesson_orders_are_placed_by_business_accounts(built):
    found, volume = built
    assert volume.key is not None
    business = set(volume.key.business)
    by_handle = {
        s.action.handle: s.action.customer for s in volume.steps if isinstance(s.action, Place)
    }
    small = [
        x.order_no
        for x in found.lessons
        if x.bags < 10
        and x.order_no != world.CAFE
        and by_handle.get(f'lesson {x.order_no}') in business
    ]
    assert tuple(small) == MISFITS == volume.key.misfits


def test_the_script_is_embedded_unchanged_less_the_setup_stock(built):
    _, volume = built
    generated = {id(s) for s in world.generated(volume)}
    kept = [s for s in volume.steps if id(s) not in generated]
    setup_stock = [
        s
        for s in script.steps()
        if s.at.date() == script.SETUP.date() and isinstance(s.action, Roast | Stocktake)
    ]
    assert len(setup_stock) == 4
    assert kept == [s for s in script.steps() if s not in setup_stock]


WINDOW_KINDS = (Place, Pay, Ship, Deliver, NightlyExtract)
"""All a generated step in the teaching window may be (U7)."""
SHIPPED_CAST = {'O-103', 'O-108'}
"""The cast's orders the volume ships after the window; O-104 to O-107 never ship."""


def test_the_teaching_window_holds_only_other_customers_p11_p21_trade(built):
    """In [5 Oct 00:00, 10 Oct 07:00] a generated step is a Place or Pay of P-11 and P-21 lines
    by a customer registered before it, a Ship or Deliver of a generated parcel, or a
    NightlyExtract; none in the blackout before E-09's batch. After the window a generated
    Ship or Deliver may name O-103 or O-108; nothing else generated names a cast id. No step
    sits at a script moment, none makes what FORBIDDEN names, every customer step is at
    09:00-16:00 UTC, and the 240 subscribe by 30 September, any other only after the window.
    """
    _, volume = built
    moments = {s.at for s in script.steps()}
    cast = world.cast_ids()
    lo, hi = world.CUSTOMER_HOURS
    registered = {
        s.action.handle: s.at for s in world.generated(volume) if isinstance(s.action, Register)
    }
    wrong = []
    subscribes = later = 0
    for step in world.generated(volume):
        action, at = step.action, step.at
        window = world.QUIET[0] <= at <= world.QUIET[1]
        if window and not isinstance(action, WINDOW_KINDS):
            wrong.append(('in the window', step))
        if window and isinstance(action, Place):
            if {i.product_id.value for i in action.order.items} - {'P-11', 'P-21'}:
                wrong.append(('a P-10 or P-20 line in the window', step))
            if registered.get(action.customer, world.QUIET[1]) >= world.QUIET[0]:
                wrong.append(('a customer not registered before the window', step))
        if world.BLACKOUT[0] <= at < world.BLACKOUT[1]:
            wrong.append(('in the blackout', step))
        if at in moments:
            wrong.append(('at a script moment', step))
        if isinstance(action, world.FORBIDDEN):
            wrong.append(('forbidden', step))
        named = cast & set(world.names(action))
        if named and (window or not isinstance(action, Ship | Deliver) or named - SHIPPED_CAST):
            wrong.append(('names the cast', step))
        if isinstance(action, world.CUSTOMER_ACTIONS) and not lo <= at.time() <= hi:
            wrong.append(('outside 09:00-16:00 UTC', step))
        if isinstance(action, Subscribe):
            subscribes += at.date() <= world.COUNTED_ON
            later += at > world.QUIET[1]
    assert wrong[:5] == []
    assert subscribes == 240
    assert later > 0
    assert subscribes + later == sum(
        isinstance(s.action, Subscribe) for s in world.generated(volume)
    )
    assert volume.refuse == script.REFUSE


def test_the_volume_ships_the_cast_orders_it_may(built):
    """C-01's 17 year orders ship the next day at 09:00-16:00 UTC; O-103 and O-108 on 12 October;
    each is delivered one to three days on (U7)."""
    _, volume = built
    ships = {s.action.order_id: s.at for s in world.generated(volume) if isinstance(s.action, Ship)}
    delivered = {
        s.action.order_id: s.at for s in world.generated(volume) if isinstance(s.action, Deliver)
    }
    year = [(f'year {n}', day) for n, (day, _) in enumerate(script.YEAR, 1)]
    cast = [(OrderId(o), dt.date(2026, 10, 12)) for o in sorted(SHIPPED_CAST)]
    for order, day in [*year, *cast]:
        at = ships[order]
        assert at.date() == (day + dt.timedelta(days=1) if order in dict(year) else day)
        assert dt.time(9) <= at.time() < dt.time(16)
        assert 1 <= (delivered[order].date() - at.date()).days <= 3
    assert not {OrderId(o) for o in ('O-104', 'O-105', 'O-106', 'O-107')} & set(ships)


def test_walk_ins_ring_nothing_the_stock_holds(built):
    """After the week the till rings loose P-11 by weight and the code with no product (U7)."""
    _, volume = built
    walk_ins = {r.receipt_id for r in volume.till_receipts if r.member_no is None} - {'R-5001'}
    found = {
        (line.ean, line.grams is None) for line in volume.till_lines if line.receipt_id in walk_ins
    }
    assert found == {('2100000000111', False), ('2000000000992', True)}
