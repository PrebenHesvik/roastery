"""The claims are complete and nothing is skipped (6.1 S6).

The claims are read from the test files' functions, and which of them await data on the
baseline is computed from the contract and a built baseline, not from this run of pytest (which
may be given other data folders).
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

from roastery_spec import baseline
from roastery_spec.claims import Claim, awaiting, claim_of
from roastery_spec.contract import TABLES

TESTS = Path(__file__).parent
SPEC = TESTS.parent
NEW_TABLES = TESTS / 'test_new_tables.py'
# Built so that this line does not match itself.
FORBIDDEN = re.compile(
    'pytest' + r'\.(skip|xfail|importorskip)\(|mark' + r'\.(skip|skipif|xfail)\b'
)


def _tests_of(path: Path) -> dict[str, object]:
    spec = importlib.util.spec_from_file_location(f'_claims_meta_{path.stem}', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: value for name, value in vars(module).items() if name.startswith('test_')}


def _claims() -> dict[str, Claim]:
    found: dict[str, Claim] = {}
    for path in sorted(TESTS.glob('test_*.py')):
        if path.name == Path(__file__).name:
            continue
        for name, test in _tests_of(path).items():
            claimed = claim_of(test)
            if claimed:
                assert name not in found, f'two claims named {name}'
                found[name] = claimed
    return found


def _new_needs() -> set[str]:
    """The 1.0 tables, and the 1.0 columns of baseline tables as table.column."""
    needs = {t.name for t in TABLES if t.since == '1.0'}
    needs |= {f'{t.name}.{c.name}' for t in TABLES for c in t.added}
    return needs


def test_every_test_in_test_new_tables_is_a_claim():
    tests = _tests_of(NEW_TABLES)
    assert tests
    assert [name for name, test in tests.items() if claim_of(test) is None] == []


def test_every_claim_takes_its_extract_as_a_fixture():
    for path in sorted(TESTS.glob('test_*.py')):
        for name, test in _tests_of(path).items():
            claimed = claim_of(test)
            if claimed:
                assert claimed.extract in inspect.signature(test).parameters, name


def test_every_claim_names_a_table_of_the_contract():
    known = {t.name for t in TABLES} | _new_needs()
    for name, claimed in _claims().items():
        assert set(claimed.tables) <= known, name


def test_every_new_table_and_column_has_a_claim():
    claimed = {need for c in _claims().values() for need in c.tables}
    assert sorted(_new_needs() - claimed) == []


def test_the_claims_awaiting_data_on_the_baseline_are_exactly_the_new_tables(tmp_path):
    claims = _claims()
    baseline.build(tmp_path)
    expected = {name for name, c in claims.items() if set(c.tables) & _new_needs()}
    built = {name for name, c in claims.items() if awaiting(c.tables, tmp_path)}
    unbuilt = {name for name, c in claims.items() if awaiting(c.tables, None)}
    assert expected
    assert built == expected
    assert unbuilt == expected


def test_nothing_in_the_spec_is_skipped():
    found = []
    for path in sorted(SPEC.rglob('*.py')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if FORBIDDEN.search(line):
                found.append(f'{path.relative_to(SPEC).as_posix()}:{number}')
    assert found == []
