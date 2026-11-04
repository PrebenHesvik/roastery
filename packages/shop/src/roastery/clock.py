"""Days from moments: the clock's pure half (ADR 0008).

The `Clock` port gives a moment in UTC; the day it falls on depends
on whose clock it is, so a day is always worked out from a moment
and a zone.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final
from zoneinfo import ZoneInfo

from roastery.ids import Country

ZONES: Final[Mapping[Country, ZoneInfo]] = MappingProxyType(
    {
        'DK': ZoneInfo('Europe/Copenhagen'),
        'FI': ZoneInfo('Europe/Helsinki'),
        'NO': ZoneInfo('Europe/Oslo'),
        'SE': ZoneInfo('Europe/Stockholm'),
    }
)
"""The zone of each country. A key it lacks raises: no fallback."""


def local_date(now: dt.datetime, zone: ZoneInfo) -> dt.date:
    """The day `now` falls on in `zone`; `now` must be aware."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone-aware')
    return now.astimezone(zone).date()
