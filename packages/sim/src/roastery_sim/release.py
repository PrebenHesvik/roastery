"""The release's zips: `roastery-data-VERSION-{tiny,month,full}.zip`, byte for byte repeatable.

Entries are sorted, carry a fixed timestamp (1980-01-01, the zip format's earliest), fixed
permissions and deflate at one level; each sits under a folder named for its zip. A folder is
zipped only when its manifest is the zip's own (its `extract` the zip's part, no `until`, and
`version` this release's) and its files are the ones the manifest names, each with its sha256:
the data folder's `manifest.json` lists its parquet files, and month's lists its landing too.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

VERSION = '1.0.0'
_STAMP = (1980, 1, 1, 0, 0, 0)

TINY_FILES: Final = ('tiny.sql', 'landing/raw_customers.csv', 'landing/raw_lines.csv')
"""Tiny's files beside its data folder, which its manifest does not list (its bytes are
frozen); they are held to being there, by name."""
UNVERSIONED: Final = ('tiny',)
"""The parts whose manifest has no `version`: tiny's bytes were frozen before there was one
(`tiny.sha256`). A version it does give must be this release's."""


def _refused(part: str, manifest: Mapping[str, object]) -> list[str]:
    """What makes the manifest another zip's: a wrong extract, a cut play, another version."""
    wrong = []
    if manifest.get('extract') != part:
        wrong.append(f'extract {manifest.get("extract")!r}, not {part!r}')
    if manifest.get('until') is not None:
        wrong.append(f'a play cut at {manifest["until"]}')
    if 'version' in manifest or part not in UNVERSIONED:
        if manifest.get('version') != VERSION:
            wrong.append(f'version {manifest.get("version")!r}, not {VERSION!r}')
    return wrong


def expected(folder: Path, *, part: str, extra: Iterable[str] = ()) -> dict[str, str | None]:
    """The files a built folder must hold, by path under it, with the sha256 its manifest
    gives each (None for a file held by name only: the manifest itself and `extra`).

    A manifest that is not `part`'s of this release (`_refused`) is refused, naming why.
    """
    path = folder / 'data' / 'manifest.json'
    if not path.is_file():
        raise FileNotFoundError(f'{folder.name}: no data/manifest.json')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    wrong = _refused(part, manifest)
    if wrong:
        raise ValueError(f'{folder.name}: its manifest is not {part} {VERSION}: {"; ".join(wrong)}')
    files: dict[str, str | None] = {'data/manifest.json': None}
    files.update({f'data/{name}': sha for name, sha in manifest['sha256'].items()})
    files.update({f'landing/{name}': sha for name, sha in manifest.get('landing', {}).items()})
    files.update(dict.fromkeys(extra))
    return files


def zip_folder(target: Path, folder: Path, files: Mapping[str, str | None]) -> Path:
    """`target` holding every file under `folder`, under a folder named for the target.

    The folder must hold exactly `files` (by path under it), each with the sha256 given where
    one is; an extra file, a missing one or a different sha256 is refused, naming them.
    """
    if not folder.is_dir():
        raise FileNotFoundError(f'{folder.name}: not a built folder')
    found = {
        path.relative_to(folder).as_posix(): path for path in folder.rglob('*') if path.is_file()
    }
    extra = sorted(set(found) - set(files))
    missing = sorted(set(files) - set(found))
    changed = sorted(
        name
        for name, sha in files.items()
        if sha is not None
        and name in found
        and hashlib.sha256(found[name].read_bytes()).hexdigest() != sha
    )
    wrong = [
        f'{what} {names[:5]}'
        for what, names in (('extra', extra), ('missing', missing), ('another sha256', changed))
        if names
    ]
    if wrong:
        raise ValueError(f'{folder.name} differs from its manifest: {"; ".join(wrong)}')
    entries = sorted((f'{target.stem}/{name}', path) for name, path in found.items())
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w') as archive:
        for name, path in entries:
            info = zipfile.ZipInfo(name, _STAMP)
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED, 6)
    return target


def release(out: Path, *, tiny: Path, volume: Path) -> tuple[Path, ...]:
    """The three zips in `out`, from the built tiny folder and the built volume folder.

    Month is its `data` and its `landing`; full is its `data`.
    """
    stem = f'roastery-data-{VERSION}'
    month, full = volume / 'month', volume / 'full'
    return (
        zip_folder(out / f'{stem}-tiny.zip', tiny, expected(tiny, part='tiny', extra=TINY_FILES)),
        zip_folder(out / f'{stem}-month.zip', month, expected(month, part='month')),
        zip_folder(out / f'{stem}-full.zip', full, expected(full, part='full')),
    )
