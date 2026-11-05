"""The volume's world (6.5, U3): the quiet window, feasibility on the real targets, V6's 13."""

from __future__ import annotations

import pytest
from roastery_sim import script, targets, world
from roastery_sim.script import NightlyExtract, Place, Roast, Stocktake, Subscribe

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


def test_no_generated_step_in_the_quiet_window_at_a_script_moment_or_naming_the_cast(built):
    _, volume = built
    moments = {s.at for s in script.steps()}
    cast = world.cast_ids()
    lo, hi = world.CUSTOMER_HOURS
    wrong = []
    subscribes = 0
    for step in world.generated(volume):
        action = step.action
        if world.QUIET[0] <= step.at <= world.QUIET[1] and not isinstance(action, NightlyExtract):
            wrong.append(('in the window', step))
        if step.at in moments:
            wrong.append(('at a script moment', step))
        if isinstance(action, world.FORBIDDEN):
            wrong.append(('forbidden', step))
        if cast & set(world.names(action)):
            wrong.append(('names the cast', step))
        if isinstance(action, world.CUSTOMER_ACTIONS) and not lo <= step.at.time() <= hi:
            wrong.append(('outside 09:00-16:00 UTC', step))
        subscribes += isinstance(action, Subscribe)
    assert wrong[:5] == []
    assert subscribes == 240
    assert volume.refuse == script.REFUSE
