"""A fresh API on temp sqlite files, seeded, at a fixed moment."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from roastery.fakes import FakeClock
from roastery_api.__main__ import seed
from roastery_api.app import create_app
from roastery_api.live import Live, open_live

NOW = dt.datetime(2026, 11, 7, 12, 0, tzinfo=dt.UTC)
"""A Saturday: P-10 at 129.00, P-20 at 899.00, no campaign running."""


def env_for(folder: Path) -> dict[str, str]:
    return {
        'ROASTERY_DATABASE_URL': f'sqlite:///{(folder / "shop.db").as_posix()}',
        'SHOP_API_STATE_URL': f'sqlite:///{(folder / "state.db").as_posix()}',
    }


@pytest.fixture
def fresh_env(tmp_path: Path) -> dict[str, str]:
    """The environment of an empty pair of dbs."""
    return env_for(tmp_path)


@pytest.fixture
def wall() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def env(fresh_env: dict[str, str]) -> dict[str, str]:
    assert seed(fresh_env)
    return fresh_env


@pytest.fixture
def live(env: dict[str, str], wall: FakeClock) -> Iterator[Live]:
    wired, _ = open_live(env, wall=wall)
    yield wired
    wired.close()


@pytest.fixture
def client(live: Live) -> Iterator[TestClient]:
    with TestClient(create_app(live, sandbox=True)) as http:
        yield http
