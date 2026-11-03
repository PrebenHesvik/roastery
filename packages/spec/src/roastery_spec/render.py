"""Render the contract's tables into the marked regions of `contract.md`.

`python -m roastery_spec.render` rewrites the regions in place; the prose around them is
written by hand and kept. A region runs from `<!-- tables:<name>:start -->` to
`<!-- tables:<name>:end -->`, one per tier.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from roastery_spec.contract import TABLES, Table

CONTRACT_MD = Path(__file__).resolve().parents[2] / 'contract.md'

REGIONS = {'tier-1': 1, 'tier-2': 2, 'tier-3': 3, 'new': 'new'}

_REGION = re.compile(
    r'<!-- tables:(?P<name>[\w-]+):start -->\n(?P<body>.*?)<!-- tables:(?P=name):end -->',
    re.DOTALL,
)


def render_table(table: Table) -> list[str]:
    """The lines of one table's block: a heading, its fields, its columns, its meaning."""
    key = ', '.join(table.key) if table.key else 'none'
    lines = [
        f'### `{table.name}`',
        '',
        f'- **grain:** {table.grain}',
        f'- **key:** `{key}`',
        f'- **system:** {table.system}',
        f'- **tiny:** {table.cut}',
        f'- **lives in:** {table.lives_in or "not in tiny"}',
        f'- **extracts:** {", ".join(table.extracts)}',
        f'- **since:** {table.since}',
        '',
        '| column | type |',
        '|---|---|',
    ]
    lines += [f'| {c.name} | {c.type} |' for c in table.columns]
    lines += [f'| {c.name} | {c.type}, month and full only (1.0) |' for c in table.added]
    lines += ['', f'**What it is.** {table.definition}', '', '**Lessons**', '']
    lines += [f'- `{page}`: {need}' for page, need in table.lessons]
    return lines


def render_regions() -> dict[str, str]:
    """What each marked region of `contract.md` should hold, by region name."""
    regions = {}
    for name, tier in REGIONS.items():
        blocks = ['\n'.join(render_table(t)) for t in TABLES if t.tier == tier]
        regions[name] = '\n' + '\n\n'.join(blocks) + '\n\n'
    return regions


def regions_in(text: str) -> dict[str, str]:
    """The regions a `contract.md` text holds now, by region name."""
    return {m['name']: m['body'] for m in _REGION.finditer(text)}


def blocks(region: str) -> dict[str, list[str]]:
    """A region's lines split into one block per table, by table name."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in region.splitlines():
        head = re.fullmatch(r'### `(\w+)`', line)
        if head:
            current = found.setdefault(head[1], [])
        if current is not None:
            current.append(line)
    return found


def rewrite(text: str) -> str:
    """The text with every region replaced by what the contract renders."""
    wanted = render_regions()
    missing = sorted(set(wanted) - set(regions_in(text)))
    if missing:
        raise ValueError(f'contract.md lacks the regions {missing}')

    def fill(match: re.Match[str]) -> str:
        name = match['name']
        return f'<!-- tables:{name}:start -->\n{wanted[name]}<!-- tables:{name}:end -->'

    return _REGION.sub(fill, text)


def main(path: Path = CONTRACT_MD) -> None:
    """Rewrite the regions of `contract.md`, with LF line ends."""
    text = path.read_text(encoding='utf-8')
    path.write_bytes(rewrite(text).encode('utf-8'))


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else CONTRACT_MD)
