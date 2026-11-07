"""`python -m roastery_api seed`: the simulator's catalogue into an empty shop db (ADR 0016).

The shop db is `ROASTERY_DATABASE_URL`'s, the state db `SHOP_API_STATE_URL`'s: the seed's
movement ids come from the state db's counter, so the server's later ids go on after them;
the counters are first raised past the ids the shop db holds.
`roastery-sim` is a dev dependency, imported inside the command only.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

from roastery.settings import SettingsError

from roastery_api.settings import ApiSettings, shop_settings
from roastery_api.state import CountedIds, State, connect, floor_counters


def seed(env: Mapping[str, str]) -> bool:
    """Seed the shop db `env` names; True if it was empty and is now seeded."""
    from roastery_sim.seed import catalogue  # a dev dependency: the server never imports it

    settings = shop_settings(env)
    api = ApiSettings.from_env(env)
    shop = connect(settings.database_url)
    state = connect(api.state_url)
    try:
        counted = State(state)
        floor_counters(counted, shop)
        return catalogue(shop, then=CountedIds(counted))
    finally:
        shop.close()
        state.close()


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    parser = argparse.ArgumentParser(prog='roastery_api', description="The API's commands.")
    parser.add_argument('command', choices=('seed',))
    parser.parse_args(list(argv))
    try:
        done = seed(env)
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    print('seeded the catalogue' if done else 'the catalogue is not empty: nothing seeded')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:], os.environ))
