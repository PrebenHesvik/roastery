"""The volume's bytes are held the way tiny's are: by the sha256 of each manifest, which lists
every parquet file's sha256 (and month's every landing file's). The zips of a release are
repeatable, and made only of folders that match their manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from roastery_sim import build, folder, release
from roastery_sim.__main__ import main

SHA_FILE = Path(__file__).with_name('volume.sha256')
PINNED = dict.fromkeys(folder.PACKAGES, 'sha-gate')
"""The package versions the pinned manifests name: fixed, so a version bump moves no byte."""


def test_the_volume_bytes_are_those_committed(volume: build.PlayedVolume, tmp_path: Path) -> None:
    build.write_volume(volume, tmp_path, seed=0, packages=PINNED)
    got = {
        name: hashlib.sha256((tmp_path / name / 'data' / 'manifest.json').read_bytes()).hexdigest()
        for name in ('full', 'month')
    }
    committed = dict(line.split(' ') for line in SHA_FILE.read_text(encoding='utf-8').splitlines())
    assert got == committed, (
        f'a volume manifest changed: now full {got["full"]} and month {got["month"]}. If this is '
        'on purpose, rewrite tests/volume.sha256 as two lines, "full <hex>" and "month <hex>" (LF).'
    )


def test_the_volume_manifests_name_their_provenance(
    volume: build.PlayedVolume, tmp_path: Path
) -> None:
    build.write_volume(volume, tmp_path, seed=0, packages=PINNED)
    for name in ('full', 'month'):
        manifest = json.loads((tmp_path / name / 'data' / 'manifest.json').read_text('utf-8'))
        assert manifest['version'] == release.VERSION
        assert manifest['packages'] == PINNED
        assert set(manifest['baseline']) == {'dataset.sql', 'tier3.sql'}
        assert ('landing' in manifest) == (name == 'month')
    landing = tmp_path / 'month' / 'landing'
    files = sorted(p.relative_to(landing).as_posix() for p in landing.rglob('*') if p.is_file())
    assert sorted(manifest['landing']) == files


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _built(root: Path, files: dict[str, str], *, landing: dict[str, str] | None = None) -> Path:
    """A built folder: `data/` with the files and a manifest naming them, and a landing. The
    manifest is its part's (the folder's name) of this release; tiny's has no version, as
    tiny's own."""
    manifest: dict[str, object] = {'extract': root.name, 'until': None}
    if root.name != 'tiny':
        manifest['version'] = release.VERSION
    manifest['sha256'] = {n: _sha(t) for n, t in files.items()}
    if landing is not None:
        manifest['landing'] = {n: _sha(t) for n, t in landing.items()}
    texts = {f'data/{n}': t for n, t in files.items()}
    texts |= {f'landing/{n}': t for n, t in (landing or {}).items()}
    texts['data/manifest.json'] = json.dumps(manifest)
    for name, text in texts.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(text.encode('utf-8'))
    return root


def _folders(tmp_path: Path) -> tuple[Path, Path]:
    tiny = _built(tmp_path / 'tiny', {'b.parquet': 'b' * 5000, 'a.parquet': 'a'})
    for name in release.TINY_FILES:
        (tiny / name).parent.mkdir(parents=True, exist_ok=True)
        (tiny / name).write_text(name, encoding='utf-8')
    volume = tmp_path / 'volume'
    _built(volume / 'full', {'x.parquet': 'full'})
    _built(volume / 'month', {'x.parquet': 'month'}, landing={'loads.json': '[]\n'})
    return tiny, volume


def test_two_releases_of_the_same_folders_are_the_same_bytes(tmp_path: Path) -> None:
    tiny, volume = _folders(tmp_path)
    for run in ('one', 'two'):
        args = ['release', '--out', str(tmp_path / run), '--tiny', str(tiny)]
        assert main([*args, '--volume', str(volume)]) == 0
    names = sorted(p.name for p in (tmp_path / 'one').iterdir())
    assert names == [
        f'roastery-data-{release.VERSION}-{part}.zip' for part in ('full', 'month', 'tiny')
    ]
    for name in names:
        assert (tmp_path / 'one' / name).read_bytes() == (tmp_path / 'two' / name).read_bytes()


@pytest.mark.parametrize(
    ('path', 'change', 'reason'),
    [
        ('volume/month/landing/stale.csv', 'write', 'extra'),
        ('volume/full/data/x.parquet', 'delete', 'missing'),
        ('volume/month/landing/loads.json', 'write', 'another sha256'),
        ('tiny/tiny.sql', 'delete', 'missing'),
    ],
)
def test_a_folder_that_differs_from_its_manifest_is_not_zipped(
    tmp_path: Path, path: str, change: str, reason: str
) -> None:
    tiny, volume = _folders(tmp_path)
    if change == 'write':
        (tmp_path / path).write_text('changed', encoding='utf-8')
    else:
        (tmp_path / path).unlink()
    with pytest.raises(ValueError, match=reason):
        release.release(tmp_path / 'out', tiny=tiny, volume=volume)


@pytest.mark.parametrize(
    ('part', 'change', 'reason'),
    [
        ('volume/month', {'extract': 'full'}, "extract 'full', not 'month'"),
        ('volume/full', {'until': '2026-10-05T00:00:00+00:00'}, 'a play cut at 2026-10-05'),
        ('volume/full', {'version': '0.9.0'}, "version '0.9.0', not"),
        ('volume/month', {'version': None}, 'version None, not'),
        ('tiny', {'version': '0.9.0'}, "version '0.9.0', not"),
        ('tiny', {'until': '2026-10-05T00:00:00+00:00'}, 'a play cut at'),
    ],
)
def test_a_manifest_not_of_its_zip_is_not_zipped(
    tmp_path: Path, part: str, change: dict[str, object], reason: str
) -> None:
    """A folder is zipped only under its own part, of a whole play, of this release's version;
    tiny's manifest may give no version (its bytes are frozen), but not another."""
    tiny, volume = _folders(tmp_path)
    path = tmp_path / part / 'data' / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for key, value in change.items():
        if value is None:
            manifest.pop(key)
        else:
            manifest[key] = value
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match=reason):
        release.release(tmp_path / 'out', tiny=tiny, volume=volume)
