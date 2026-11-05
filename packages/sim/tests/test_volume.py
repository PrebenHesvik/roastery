"""The volume's bytes are held the way tiny's are: by the sha256 of each manifest, which lists
every parquet file's sha256. The zips of a release are repeatable."""

from __future__ import annotations

import hashlib
from pathlib import Path

from roastery_sim import build, release
from roastery_sim.__main__ import main

SHA_FILE = Path(__file__).with_name('volume.sha256')


def test_the_volume_bytes_are_those_committed(volume: build.PlayedVolume, tmp_path: Path) -> None:
    build.write_volume(volume, tmp_path, seed=0, shop_version='sha-gate')
    got = {
        name: hashlib.sha256((tmp_path / name / 'data' / 'manifest.json').read_bytes()).hexdigest()
        for name in ('full', 'month')
    }
    committed = dict(line.split(' ') for line in SHA_FILE.read_text(encoding='utf-8').splitlines())
    assert got == committed, (
        f'a volume manifest changed: now full {got["full"]} and month {got["month"]}. If this is '
        'on purpose, rewrite tests/volume.sha256 as two lines, "full <hex>" and "month <hex>" (LF).'
    )


def test_two_releases_of_the_same_folders_are_the_same_bytes(tmp_path: Path) -> None:
    tiny = tmp_path / 'tiny'
    (tiny / 'data').mkdir(parents=True)
    (tiny / 'data' / 'b.parquet').write_bytes(b'b' * 5000)
    (tiny / 'data' / 'a.parquet').write_bytes(b'a')
    for name in ('full/data', 'month/data', 'month/landing'):
        (tmp_path / 'volume' / name).mkdir(parents=True)
        (tmp_path / 'volume' / name / 'x.csv').write_text(name, encoding='utf-8')
    for run in ('one', 'two'):
        args = ['release', '--out', str(tmp_path / run), '--tiny', str(tiny)]
        assert main([*args, '--volume', str(tmp_path / 'volume')]) == 0
    names = sorted(p.name for p in (tmp_path / 'one').iterdir())
    assert names == [
        f'roastery-data-{release.VERSION}-{part}.zip' for part in ('full', 'month', 'tiny')
    ]
    for name in names:
        assert (tmp_path / 'one' / name).read_bytes() == (tmp_path / 'two' / name).read_bytes()
