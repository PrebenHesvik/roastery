"""The volume's one play, shared by the tests that need it (about 30 s)."""

from __future__ import annotations

import pytest
from roastery_sim import build


@pytest.fixture(scope='session')
def volume() -> build.PlayedVolume:
    """The volume's world played once on sqlite, with `full`'s snapshot."""
    return build.play_volume(seed=0)
