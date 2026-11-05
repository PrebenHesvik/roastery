"""Tiny built from one play, and written out: the whole pipeline in one call (6.4, W1).

`build` plays, applies the export writer's faults, assembles and renders tiny, and cuts the
defect log with it; `__main__`, the gate's test and the determinism test all call it. `write`
puts what it built on disk: `tiny.sql`, the data folder and the faulted csv files of the
landing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from roastery.pipeline import Rows

from roastery_sim import dataset_sql, extracts, faults, folder, play, targets, tiny, world


@dataclass(frozen=True)
class Built:
    """Tiny's text, the defects its cut holds, and the landing's csv files by file name."""

    text: str
    defects: tuple[faults.Defect, ...]
    landing: Mapping[str, str]


def _raw_key(value: object) -> object:
    """A raw cell as the cut matches it: blanks, a tab or a no-break space around the id, and
    its case, do not count."""
    return value.strip().upper() if isinstance(value, str) else value


def _in(rows: Rows, entry: faults.Defect) -> bool:
    """Whether the entry's row is in the table; a raw id matched as tiny cuts it (W33)."""
    if entry.table in tiny.RAW:
        at = rows.columns.index(faults.TABLE_KEYS[entry.table][0])
        return any(_raw_key(row[at]) == entry.key for row in rows.rows)
    return any(faults.key_of(rows, row) == entry.key for row in rows.rows)


def cut(log: Sequence[faults.Defect], assembled: Sequence[Rows]) -> tuple[faults.Defect, ...]:
    """The entries of the log that tiny holds (W39): the entry's row is in tiny's table, or,
    for a dropped order's events, the order is one of the cast's."""
    tables = {rows.name: rows for rows in assembled}
    kept = []
    for entry in log:
        if entry.kind == 'dropped':
            if entry.key in tiny.ORDERS:
                kept.append(entry)
        elif _in(tables[entry.table], entry):
            kept.append(entry)
    return tuple(kept)


def build(
    *,
    seed: int = 0,
    until: dt.datetime | None = None,
    store: Literal['memory', 'sqlite'] = 'memory',
) -> Built:
    """Play, fault, assemble and render tiny, its defects cut with it.

    A play cut short by `until` is not faulted (W39): its defects are none and its landing is
    the clean export, a header alone if the export had not run.
    """
    given = tiny.inputs(play.play(seed=seed, until=until, store=store))
    if until is None:
        tables, log = faults.apply(given)
    else:
        tables, log = given, ()
    assembled = tiny.assemble(tables)
    landing = {f'{name}.csv': faults.csv_text(tables[name]) for name in tiny.RAW}
    return Built(
        text=dataset_sql.render(assembled, seed=seed),
        defects=cut(log, assembled),
        landing=MappingProxyType(landing),
    )


def _bytes(path: Path, text: str) -> Path:
    """The text written as UTF-8 with its own line ends (LF), never the machine's."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    return path


def write(
    built: Built,
    out: Path,
    *,
    seed: int,
    shop_version: str,
    until: dt.datetime | None = None,
) -> tuple[Path, ...]:
    """`out/tiny.sql`, the data folder `out/data` and `out/landing/*.csv`; the files written.

    The data folder's files are its parquet files and its manifest, by name. A play stopped at
    `until` is marked so in the manifest, the moment in UTC as ISO text.
    """
    written = [_bytes(out / 'tiny.sql', built.text)]
    data = out / 'data'
    manifest = folder.write(
        built.text,
        data,
        extract='tiny',
        seed=seed,
        until=None if until is None else until.astimezone(dt.UTC).isoformat(),
        defects=[d.as_dict() for d in built.defects],
        shop_version=shop_version,
    )
    written += [data / name for name in manifest['sha256']]
    written.append(data / 'manifest.json')
    written += [_bytes(out / 'landing' / name, text) for name, text in built.landing.items()]
    return tuple(written)


@dataclass(frozen=True)
class PlayedVolume:
    """The volume's world, its one play and the targets it was fitted to."""

    world: world.Volume
    played: play.Played
    targets: targets.Targets


def play_volume(*, seed: int = 0) -> PlayedVolume:
    """Build the world from the targets and play it to the end on sqlite, with the snapshot
    `full` is cut from."""
    fitted = targets.build()
    built = world.build(fitted, seed=seed)
    played = play.play(built, seed=seed, store='sqlite', snapshots=(extracts.SNAPSHOT,))
    return PlayedVolume(built, played, fitted)


def write_volume(
    volume: PlayedVolume, out: Path, *, seed: int, shop_version: str
) -> tuple[Path, ...]:
    """`out/full/data` and `out/month/data`, each its parquet files and manifest; the files
    written."""
    events = extracts.scripted_events(volume.world, volume.played)
    written: list[Path] = []
    for extract in (
        extracts.full(volume.world, volume.played, volume.targets),
        extracts.month(volume.world, volume.played),
    ):
        data = out / extract.name / 'data'
        manifest = folder.write_rows(
            extract.tables,
            data,
            extract=extract.name,
            seed=seed,
            shop_version=shop_version,
            defects=[d.as_dict() for d in extract.defects],
            scripted_events=events,
        )
        written += [data / name for name in manifest['sha256']]
        written.append(data / 'manifest.json')
    return tuple(written)


def volume(out: Path, *, seed: int = 0, shop_version: str) -> tuple[Path, ...]:
    """Play the volume once and write `full` and `month` under `out`; the files written."""
    return write_volume(play_volume(seed=seed), out, seed=seed, shop_version=shop_version)
