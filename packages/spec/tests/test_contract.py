from importlib import resources

import duckdb
import pytest
from roastery_spec import baseline, contract, render
from roastery_spec.contract import TABLES

BASELINE = [t for t in TABLES if t.since == 'baseline']
HERE = resources.files('roastery_spec') / 'baseline'


def _label(value: str) -> str:
    return value.split(': ', 1)[0]


def _tables(name: str) -> list[dict]:
    return baseline.tables(HERE.joinpath(name).read_text(encoding='utf-8'))


def _headers() -> list[dict]:
    """The key and grain of each baseline table: tier 3's from data-docs' newer file (S20)."""
    return _tables('dataset.sql') + _tables('tier3_release.sql')


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp('baseline')
    baseline.build(folder)
    return folder


# ---- well formed ----


def test_names_are_unique():
    names = [t.name for t in TABLES]
    assert len(names) == len(set(names))


def test_by_name_finds_every_table():
    assert list(contract.by_name()) == [t.name for t in TABLES]


def test_the_tables_come_tier_by_tier():
    order = [1, 2, 3, 'new']
    tiers = [order.index(t.tier) for t in TABLES]
    assert tiers == sorted(tiers)


@pytest.mark.parametrize('table', TABLES, ids=lambda t: t.name)
def test_a_table_is_well_formed(table):
    names = [c.name for c in table.columns + table.added]
    assert len(names) == len(set(names))
    assert set(table.key) <= {c.name for c in table.columns}
    assert len(names) <= 6
    assert {c.type for c in table.columns + table.added} <= set(contract.TYPES)
    assert table.since in ('baseline', '1.0')
    assert table.tier in (1, 2, 3, 'new')
    assert (table.tier == 'new') == (table.since == '1.0')
    assert _label(table.system) in contract.SYSTEMS
    assert _label(table.cut) in contract.CUTS
    assert table.extracts
    assert set(table.extracts) <= {'tiny', 'month', 'full'}
    assert table.grain.strip()
    assert table.definition.strip()
    assert all(page.strip() and need.strip() for page, need in table.lessons)


@pytest.mark.parametrize('table', BASELINE, ids=lambda t: t.name)
def test_a_baseline_table_carries_at_least_one_lesson(table):
    assert table.lessons


@pytest.mark.parametrize('table', TABLES, ids=lambda t: t.name)
def test_a_table_has_a_cut_and_a_home_exactly_when_tiny_holds_it(table):
    in_tiny = 'tiny' in table.extracts
    assert (table.cut != 'none') == in_tiny
    assert (table.lives_in is not None) == in_tiny
    if in_tiny:
        lives = table.lives_in or ''
        assert lives in ('same(month)', 'same(full)', 'landing') or (
            lives.startswith('derived(') and lives.endswith(')')
        )


def test_only_customers_and_web_events_add_a_column_and_only_in_month_and_full():
    added = {t.name: [c.name for c in t.added] for t in TABLES if t.added}
    # account_kind, not kind: it must not meet products.kind or kinds in a USING (kind) (S17)
    assert added == {'customers': ['account_kind'], 'web_events': ['visit_id']}
    for name in added:
        assert set(contract.by_name()[name].extracts) >= {'month', 'full'}


def test_web_visits_names_its_referrer_so_it_cannot_meet_the_provenance_source():
    columns = [c.name for c in contract.by_name()['web_visits'].columns]
    assert 'referrer' in columns
    assert 'source' not in columns
    events = {c.name: c.type for c in contract.by_name()['web_events'].added}
    visits = {c.name: c.type for c in contract.by_name()['web_visits'].columns}
    assert events['visit_id'] == visits['visit_id']


def test_daily_sales_carries_the_lesson_that_walk_ins_do_not_cause_it():
    lessons = dict(contract.by_name()['daily_sales'].lessons)
    assert 'Walk-ins do not cause these sales' in lessons['stats/correlation']


# ---- the baseline ----


def test_the_baseline_tables_are_the_headers_in_their_order():
    assert [t.name for t in BASELINE] == [h['name'] for h in _headers()]


@pytest.mark.parametrize('head', _headers(), ids=lambda h: h['name'])
def test_a_baseline_table_has_the_key_and_grain_of_its_header(head):
    table = contract.by_name()[head['name']]
    assert table.key == (() if head['key'] == ['none'] else tuple(head['key']))
    assert table.grain == head['grain']


def test_tier3_sql_and_its_successor_hold_the_same_tables_and_keys():
    built = [(h['name'], h['key']) for h in _tables('tier3.sql')]
    assert built == [(h['name'], h['key']) for h in _tables('tier3_release.sql')]


def test_tier_1_is_the_first_five_tables_of_dataset_sql():
    assert [t.name for t in TABLES if t.tier == 1] == [h['name'] for h in _headers()[:5]]


def test_the_build_writes_exactly_the_baseline_tables(built):
    assert sorted(p.stem for p in built.glob('*.parquet')) == sorted(t.name for t in BASELINE)


@pytest.mark.parametrize('table', BASELINE, ids=lambda t: t.name)
def test_a_built_table_has_the_contract_columns_and_types(built, table):
    path = (built / f'{table.name}.parquet').as_posix()
    with duckdb.connect() as con:
        got = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()]
    assert got == [(c.name, c.type) for c in table.columns]


# ---- contract.md ----


def test_contract_md_holds_exactly_the_rendered_regions():
    text = render.CONTRACT_MD.read_text(encoding='utf-8')
    held = render.regions_in(text)
    wanted = render.render_regions()
    assert sorted(held) == sorted(wanted)
    for region, body in wanted.items():
        want = render.blocks(body)
        have = render.blocks(held[region])
        assert list(have) == list(want), f'{region}: the tables or their order differ'
        for name, lines in want.items():
            for i, line in enumerate(lines):
                got = have[name][i] if i < len(have[name]) else '<missing>'
                assert got == line, f'{name}, line {i + 1}: contract.md has {got!r}, not {line!r}'
            assert len(have[name]) == len(lines), f'{name}: contract.md has extra lines'
        assert held[region].splitlines() == body.splitlines(), f'{region}: text between tables'


def test_the_prose_names_every_system():
    text = render.CONTRACT_MD.read_text(encoding='utf-8')
    for name in render.regions_in(text).values():
        text = text.replace(name, '')
    assert [s for s in contract.SYSTEMS if f'| {s} |' not in text] == []


def test_a_render_changes_nothing():
    text = render.CONTRACT_MD.read_text(encoding='utf-8')
    assert render.rewrite(text) == text
