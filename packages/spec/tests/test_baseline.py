import hashlib
import json
from importlib import resources
from pathlib import Path

from roastery_spec import baseline

TIER3 = {
    'daily_sales': 1947,
    'order_values': 600,
    'budget': 54,
    'checkout_test': 4000,
    'subscribers': 240,
    'visits': 3600,
    'deliveries': 480,
    'shop_days': 730,
}


def _files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_the_copies_are_the_files_their_provenance_names():
    origin = baseline.provenance()
    assert origin['commit'] == 'd23336d'
    here = resources.files('roastery_spec') / 'baseline'
    for key in ('dataset_sql', 'tier3_sql'):
        name = origin[key]['path'].rsplit('/', 1)[1]
        assert hashlib.sha256((here / name).read_bytes()).hexdigest() == origin[key]['sha256']


def test_a_build_writes_every_table_and_its_manifest(tmp_path):
    counts = baseline.build(tmp_path)
    manifest = json.loads((tmp_path / 'manifest.json').read_text(encoding='utf-8'))
    files = sorted(p.stem for p in tmp_path.glob('*.parquet'))
    assert len(files) == 38
    assert files == sorted(manifest['tables'])
    assert manifest['tables'] == counts
    assert all(rows >= 1 for rows in counts.values())
    assert {name: counts[name] for name in TIER3} == TIER3
    assert manifest['extract'] == 'baseline'
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest


def test_a_second_build_gives_the_same_bytes(tmp_path):
    baseline.build(tmp_path / 'one')
    baseline.build(tmp_path / 'two')
    assert _files(tmp_path / 'one') == _files(tmp_path / 'two')


def test_a_build_removes_a_parquet_file_no_table_makes(tmp_path):
    stray = tmp_path / 'not_a_table.parquet'
    stray.write_bytes(b'x')
    baseline.build(tmp_path)
    assert not stray.exists()
