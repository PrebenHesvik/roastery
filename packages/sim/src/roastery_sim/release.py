"""The release's zips: `roastery-data-VERSION-{tiny,month,full}.zip`, byte for byte repeatable.

Entries are sorted, carry a fixed timestamp (1980-01-01, the zip format's earliest), fixed
permissions and deflate at one level; each sits under a folder named for its zip.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

VERSION = '1.0.0'
_STAMP = (1980, 1, 1, 0, 0, 0)


def zip_folder(target: Path, folder: Path) -> Path:
    """`target` holding every file under `folder`, under a folder named for the target."""
    if not folder.is_dir():
        raise FileNotFoundError(f'{folder.name}: not a built folder')
    entries = sorted(
        (f'{target.stem}/{path.relative_to(folder).as_posix()}', path)
        for path in folder.rglob('*')
        if path.is_file()
    )
    if not entries:
        raise FileNotFoundError(f'{folder.name}: nothing to zip')
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
    return (
        zip_folder(out / f'{stem}-tiny.zip', tiny),
        zip_folder(out / f'{stem}-month.zip', volume / 'month'),
        zip_folder(out / f'{stem}-full.zip', volume / 'full'),
    )
