"""The simulator's catalogue, written into an empty shop db (ADR 0016).

The API's `seed` command fills its own shop db with what the shop sells: the setup steps
of the script (categories, P-10 to P-21, the prices, campaigns K-1 and K-2, the opening
stock), played through the play's own dispatch at the script's moments. It reuses the
script and the play; it copies neither. The script's ids name the categories, products
and campaigns; every other id (the stock's movements) is drawn from `then`, the caller's
counter, so the ids the API draws later never meet them.
"""

from __future__ import annotations

import sqlite3

from roastery.bootstrap import sqlite_store, wire
from roastery.fakes import FakeClock, FakeLabels, FakeNotifier, FakeProvider
from roastery.ports import Ids
from roastery.repository import ScriptedIds
from roastery.settings import Secret, Settings, Url

from roastery_sim import play, script
from roastery_sim.feed import Feed
from roastery_sim.outside import ProviderLog


def catalogue(connection: sqlite3.Connection, *, then: Ids) -> bool:
    """Play the script's setup into the shop db on `connection`; True if it did.

    Runs only on an empty catalogue: a db that lists a product already is left as it is,
    and False is returned. Raises if a step's handler failed (none should: setup publishes
    no event).
    """
    steps = script._setup()
    clock = FakeClock(script.SETUP)
    settings = Settings(
        database_url=Url('sqlite:///:memory:'),
        provider_url=Url('https://provider.example.invalid'),
        provider_key=Secret('not-a-key'),
    )
    store = sqlite_store(connection, clock=clock, price_ttl=settings.price_ttl)
    with store.unit_of_work('scripted') as uow:
        if uow.catalogue.products():
            return False
    provider = FakeProvider(refund_ids=())
    app = wire(
        settings,
        store,
        clock=clock,
        ids=ScriptedIds(script.scripted_ids(steps), then),
        source='scripted',
        feed=Feed(clock, refuse={}),
        provider=provider,
        notifier=FakeNotifier(),
        labels=FakeLabels(),
    )
    state = play._State(ProviderLog(provider))
    for step in steps:
        clock.set(step.at)
        play._do(app, step, state)
    failures = app.failures()
    if failures:
        raise RuntimeError(f'the seed left handler failures: {list(failures)}')
    return True
