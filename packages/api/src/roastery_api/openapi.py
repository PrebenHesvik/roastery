"""Write the API's OpenAPI document for the storefront (ADR 0019).

Run as `uv run python -m roastery_api.openapi`. The text is sorted, LF-ended and
newline-terminated, so the same code gives the same bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from roastery_api.app import create_app

TARGET = Path(__file__).resolve().parents[4] / 'apps' / 'storefront' / 'openapi.json'
"""Where the storefront reads it, from the repository root."""


def render() -> str:
    """The document as text: sorted keys, two-space indent, one final newline."""
    document = create_app(None).openapi()
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open('w', encoding='utf-8', newline='\n') as out:
        out.write(render())


if __name__ == '__main__':
    main()
