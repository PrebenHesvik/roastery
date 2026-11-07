"""The committed document is what the app renders now (the Python side of ADR 0019's drift
check)."""

from __future__ import annotations

from roastery_api.openapi import TARGET, render


def test_committed_openapi_matches_a_fresh_render() -> None:
    committed = TARGET.read_bytes().decode('utf-8')
    assert committed == render(), 'run: uv run python -m roastery_api.openapi'


def test_render_is_stable_lf_text() -> None:
    text = render()
    assert text == render()
    assert text.endswith('}\n')
    assert '\r' not in text
